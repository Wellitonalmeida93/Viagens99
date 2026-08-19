import os
import time
import pandas as pd
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURAÇÕES DO SUPABASE
# ==========================================
SUPABASE_URL = "https://ndnwtrnjclsbihvthdrg.supabase.co"
# O 'os.environ.get' puxa a senha do cofre do GitHub
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") 
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. CONFIGURAÇÕES DO ROBÔ 99
# ==========================================
TELEFONE_99 = "41992355335"        
# Puxa a senha do portal 99 do cofre do GitHub
SENHA_99 = os.environ.get("SENHA_99")

URL_LOGIN = "https://page.didiglobal.com/public-biz/pc-login/4.0.4/index.html?appid=200114&role=5010&source=70001&lang=pt-BR&country_id=76&theme=yellow&redirectUrl=https%3A%2F%2Fb2b-api.99app.com%2Fb2x-iam%2Fv2%2Fuser%2Flogin%3Fjumpto_web%3Dhttps%3A%2F%2Fempresas.99app.com%2Fv4%2F#/"
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

# ... (Daqui para baixo, o código da função run_robot() continua EXATAMENTE IGUAL, com headless=True) ...  
def run_robot():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    with sync_playwright() as p:
        # headless=True faz o navegador rodar oculto em segundo plano!
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        print("1. [Oculto] Acessando a página de login da 99...")
        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        print("2. [Oculto] Preenchendo dados de acesso...")
        page.get_by_role("textbox", name="Insira o telefone").click()
        page.get_by_role("textbox", name="Insira o telefone").fill(TELEFONE_99)
        time.sleep(0.5)

        page.get_by_role("textbox", name="Insira sua senha").click()
        page.get_by_role("textbox", name="Insira sua senha").fill(SENHA_99)
        time.sleep(0.5)

        page.locator(".checkbox").click()
        time.sleep(0.5)
        page.get_by_text("Entrar", exact=True).click()
        
        print("3. [Oculto] Aguardando o painel carregar...")
        page.wait_for_url("**/empresas.99app.com/**", timeout=60000)
        time.sleep(2)

        print("4. [Oculto] Navegando e Filtrando...")
        page.get_by_text("Relatórios").click()
        time.sleep(3)
        page.get_by_role("button", name="Filtrar").click()
        time.sleep(2)

        print("5. [Oculto] Baixando relatório Excel...")
        with page.expect_download(timeout=60000) as download_info:
            page.get_by_role("button", name="Exportar relatório deste mês").click()
        
        download = download_info.value
        file_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
        download.save_as(file_path)
        print(f"   Download concluído: {file_path}")

        context.close()
        browser.close()
        return file_path

def process_and_upload(file_path):
    print("\n6. Processando dados do Excel e enviando para o Supabase...")
    df = pd.read_excel(file_path)

    # Tratamento da Tarifa (Remove 'R$', pontos e troca vírgula por ponto)
    df['Tarifa_Limpa'] = (
        df['Tarifa']
        .astype(str)
        .str.replace('R$', '', regex=False)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False)
        .str.strip()
    )
    df['Tarifa_Limpa'] = pd.to_numeric(df['Tarifa_Limpa'], errors='coerce')

    # Tratamento da Data (Formato DD/MM/YYYY para YYYY-MM-DD aceito pelo banco)
    df['Data_Origem_Formatada'] = pd.to_datetime(df['Data Origem'], format='%d/%m/%Y', errors='coerce').dt.strftime('%Y-%m-%d')

    # Criação do DataFrame no formato exato da sua tabela do Supabase
    df_supabase = pd.DataFrame({
        'id_corrida': df['ID da Corrida'].astype(str),
        'empresa': df['Empresa'],
        'centro_custo': df['Centro de Custo'],
        'projeto': df['Projeto'],
        'solicitante': df['Solicitante'],
        'nome_colaborador': df['Nome Colaborador'],
        'email_colaborador': df['Email Colaborador'],
        'justificativa': df['Justificativa'],
        'tarifa': df['Tarifa_Limpa'],
        'plataforma': df['Plataforma de chamada (web/app)'],
        'data_origem': df['Data_Origem_Formatada'],
        'hora_origem': df['Hora Origem'],
        'cidade_origem': df['Cidade Origem'],
        'endereco_origem': df['Endereço de Origem Real'],
        'endereco_destino': df['Endereço Final Real'],
        'km': pd.to_numeric(df['Odometro (km)'], errors='coerce'),
        'duracao_min': pd.to_numeric(df['Duração (min)'], errors='coerce'),
        'categoria': df['Categoria']
    })

    # Converte os valores nulos do Pandas para None (padrão do banco de dados)
    records = df_supabase.where(pd.notnull(df_supabase), None).to_dict(orient='records')

    # Envia via upsert (se a corrida já existir, ele só atualiza, não duplica)
    response = supabase.table('historico_viagens_99').upsert(records, on_conflict='id_corrida').execute()
    
    print("="*60)
    print(f" SUCESSO TOTAL! {len(records)} viagens gravadas no Supabase.")
    print("="*60)

if __name__ == "__main__":
    arquivo = run_robot()
    if arquivo and os.path.exists(arquivo):
        process_and_upload(arquivo)
