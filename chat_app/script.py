from dotenv import load_dotenv
import smtplib
import os

load_dotenv()

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(os.getenv('SERVER_EMAIL'), os.getenv('APP_PASSWORD'))
    server.quit()
    print("Conexão SMTP bem-sucedida!")
except Exception as e:
    print(f"Erro na conexão SMTP: {e}")