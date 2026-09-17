import os
import time
import re
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine, text

# ==========================================
# 1. CONFIGURAÇÕES DO NEON (POSTGRESQL)
# ==========================================
# Puxa exclusivamente do Cofre de Segredos (GitHub Secrets)
DB_HOST = os.environ.get("DB_HOST_SUPA")
DB_PORT = os.environ.get("DB_PORT_SUPA", "5432")
DB_NAME = os.environ.get("DB_NAME_SUPA")
DB_USER = os.environ.get("DB_USER_SUPA")
DB_PASSWORD = os.environ.get("DB_PASSWORD_SUPA")

# Validação para garantir que as variáveis do GitHub Secrets foram carregadas
if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError("ERRO: Uma ou mais variáveis de ambiente do banco de dados não foram encontradas nas Secrets!")

# String de conexão do PostgreSQL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"
engine = create_engine(DATABASE_URL)

# ==========================================
# 2. CONFIGURAÇÕES DO ROBÔ 99
# ==========================================
TELEFONE_99 = "41992355335"        
SENHA_99 = os.environ.get("SENHA_99")

URL_LOGIN = "https://page.didiglobal.com/public-biz/pc-login/4.0.4/index.html?appid=200114&role=5010&source=70001&lang=pt-BR&country_id=76&theme=yellow&redirectUrl=https%3A%2F%2Fb2b-api.99app.com%2Fb2x-iam%2Fv2%2Fuser%2Flogin%3Fjumpto_web%3Dhttps%3A%2F%2Fempresas.99app.com%2Fv4%2F#/"
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

def run_robot():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    arquivos_baixados = []

    with sync_playwright() as p:
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

        hoje = datetime.now()
        
        # =================================================================
        # LÓGICA DE VIRADA DE MÊS (Dias 1 a 5)
        # =================================================================
        if hoje.day <= 5:
            print("5a. [Oculto] Início do mês! Alterando filtro para 'Mês passado'...")
            try:
                page.get_by_text("Mês atual", exact=True).first.click()
                time.sleep(1)
                
                page.get_by_text("Mês passado", exact=True).click()
                time.sleep(1)
                
                page.get_by_role("button", name="Filtrar").click()
                time.sleep(3)
                
                with page.expect_download(timeout=60000) as download_info_ant:
                    page.get_by_role("button", name=re.compile(r"Exportar", re.IGNORECASE)).click()
                
                download_ant = download_info_ant.value
                file_path_ant = os.path.join(DOWNLOAD_DIR, "mes_passado_" + download_ant.suggested_filename)
                download_ant.save_as(file_path_ant)
                arquivos_baixados.append(file_path_ant)
                print(f"   -> Download do MÊS PASSADO concluído: {file_path_ant}")
                
                page.get_by_text("Mês passado", exact=True).first.click() 
                time.sleep(1)
                page.get_by_text("Mês atual", exact=True).click()
                time.sleep(1)
                page.get_by_role("button", name="Filtrar").click()
                time.sleep(3)

            except Exception as e:
                print("   -> Erro ao tentar baixar mês passado (verifique a interface):", e)

        # =================================================================
        # BAIXAR O MÊS ATUAL (Sempre executa)
        # =================================================================
        print("5b. [Oculto] Baixando relatório do 'Mês atual'...")
        with page.expect_download(timeout=60000) as download_info:
            page.get_by_role("button", name=re.compile(r"Exportar", re.IGNORECASE)).click()
        
        download = download_info.value
        file_path = os.path.join(DOWNLOAD_DIR, "mes_atual_" + download.suggested_filename)
        download.save_as(file_path)
        arquivos_baixados.append(file_path)
        print(f"   -> Download do MÊS ATUAL concluído: {file_path}")

        context.close()
        browser.close()
        
        return arquivos_baixados

def process_and_upload(file_path):
    print(f"\n6. Processando dados do arquivo: {os.path.basename(file_path)}")
    df = pd.read_excel(file_path)

    # Tratamento da Tarifa
    df['Tarifa_Limpa'] = (
        df['Tarifa']
        .astype(str)
        .str.replace('R$', '', regex=False)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False)
        .str.strip()
    )
    df['Tarifa_Limpa'] = pd.to_numeric(df['Tarifa_Limpa'], errors='coerce')

    # Tratamento da Data
    df['Data_Origem_Formatada'] = pd.to_datetime(df['Data Origem'], format='%d/%m/%Y', errors='coerce').dt.strftime('%Y-%m-%d')

    # Mapeamento do DataFrame para a estrutura da tabela
    df_neon = pd.DataFrame({
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

    if not df_neon.empty:
        table_name = 'historico_viagens_99'
        
        # Estrutura SQL de UPSERT (Insere novos e atualiza existentes com base no id_corrida)
        upsert_query = f"""
            INSERT INTO {table_name} (
                id_corrida, empresa, centro_custo, projeto, solicitante, 
                nome_colaborador, email_colaborador, justificativa, tarifa, 
                plataforma, data_origem, hora_origem, cidade_origem, 
                endereco_origem, endereco_destino, km, duracao_min, categoria
            ) VALUES (
                :id_corrida, :empresa, :centro_custo, :projeto, :solicitante, 
                :nome_colaborador, :email_colaborador, :justificativa, :tarifa, 
                :plataforma, :data_origem, :hora_origem, :cidade_origem, 
                :endereco_origem, :endereco_destino, :km, :duracao_min, :categoria
            )
            ON CONFLICT (id_corrida) DO UPDATE SET
                empresa = EXCLUDED.empresa,
                centro_custo = EXCLUDED.centro_custo,
                projeto = EXCLUDED.projeto,
                solicitante = EXCLUDED.solicitante,
                nome_colaborador = EXCLUDED.nome_colaborador,
                email_colaborador = EXCLUDED.email_colaborador,
                justificativa = EXCLUDED.justificativa,
                tarifa = EXCLUDED.tarifa,
                plataforma = EXCLUDED.plataforma,
                data_origem = EXCLUDED.data_origem,
                hora_origem = EXCLUDED.hora_origem,
                cidade_origem = EXCLUDED.cidade_origem,
                endereco_origem = EXCLUDED.endereco_origem,
                endereco_destino = EXCLUDED.endereco_destino,
                km = EXCLUDED.km,
                duracao_min = EXCLUDED.duracao_min,
                categoria = EXCLUDED.categoria;
        """

        records = df_neon.where(pd.notnull(df_neon), None).to_dict(orient='records')

        with engine.begin() as connection:
            connection.execute(text(upsert_query), records)

        print("="*60)
        print(f" SUCESSO! {len(records)} viagens lidas e enviadas para o Neon.")
        print("="*60)
    else:
        print(" -> O arquivo estava vazio ou sem dados válidos. Nenhuma viagem enviada.")

if __name__ == "__main__":
    arquivos_para_processar = run_robot()
    
    for arquivo in arquivos_para_processar:
        if os.path.exists(arquivo):
            process_and_upload(arquivo)
