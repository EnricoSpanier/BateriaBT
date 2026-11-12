# Bateria BT

Mostra na barra de tarefas do Windows a bateria dos seus periféricos: dispositivos Bluetooth, Logitech
(pelo receptor ou pelo G HUB) e headsets, mouses, teclados e controles de outras marcas (Razer,
SteelSeries, HyperX, Corsair, ASUS ROG, Sony, PlayStation, Xbox, Pulsar, VGN e outras) direto por HID.

## Requisitos

- Windows 10 ou 11.
- Python 3.12 ou mais novo.

## Instalação

1. **Instale o Python.** Baixe em <https://www.python.org/downloads/windows/> e, na primeira tela do
   instalador, marque **"Add python.exe to PATH"**. Para conferir, abra o PowerShell e rode:

   ```powershell
   python --version
   ```

2. **Baixe o Bateria BT.** Com o Git:

   ```powershell
   git clone https://github.com/EnricoSpanier/BateriaBT.git
   cd BateriaBT
   ```

   Sem o Git: na página do repositório, clique em **Code → Download ZIP**, extraia a pasta e abra o
   PowerShell dentro dela.

3. **Instale as dependências:**

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. **Abra o app:**

   ```powershell
   pythonw bateria_bt.py
   ```

   O `pythonw` roda sem janela de console. O app aparece na barra de tarefas e na área de notificação.

5. **(Opcional) Iniciar com o Windows.** Abra o painel (clique no app na barra de tarefas ou, no ícone da
   área de notificação, em **Abrir painel**) e ligue **"Iniciar com o Windows"**. Isso cria um atalho na
   pasta Inicializar do seu usuário apontando para a pasta onde o app está; se mover a pasta, desligue e
   ligue a opção de novo.

## Atualizar

```powershell
git pull
python -m pip install -r requirements.txt
```

Depois feche o app (área de notificação → **Sair**) e abra de novo.

## Problemas comuns

- **Nada aparece:** confira se o dispositivo está ligado e pareado/conectado. Os mouses e fones dormindo
  não respondem: o app mantém a última porcentagem até eles acordarem.
- **Headsets Astro A50 Gen 5 / A50 X e G522:** com o G HUB aberto, a bateria vem do G HUB; sem ele, o app
  lê direto do fone.
- **Erros:** ficam em `%APPDATA%\BateriaBT\erros.log`. As configurações ficam em
  `%APPDATA%\BateriaBT\config.json`.

## Desinstalar

1. No painel, desligue **"Iniciar com o Windows"** e feche o app (**Sair**).
2. Apague a pasta do Bateria BT e, se quiser, `%APPDATA%\BateriaBT`.

## Licença

[Mozilla Public License 2.0](LICENSE). Pode usar, alterar e distribuir, inclusive junto com código
fechado; quem alterar e distribuir arquivos deste projeto precisa manter esses arquivos abertos sob a
MPL 2.0 e o aviso de copyright. Copyright (c) 2026 Enrico Spanier.
