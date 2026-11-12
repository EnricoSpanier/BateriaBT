; Instalador do Bateria BT (Inno Setup 6). Gerado por build.ps1 a partir de dist\BateriaBT.
#define AppVersion "1.0.0"

[Setup]
AppId={{6C1E2B7A-5F3D-4B8E-9A21-BA7E21A0B7B7}
AppName=Bateria BT
AppVersion={#AppVersion}
AppPublisher=Enrico Spanier
AppPublisherURL=https://github.com/EnricoSpanier/BateriaBT
DefaultDirName={localappdata}\Programs\BateriaBT
DefaultGroupName=Bateria BT
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=BateriaBT-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
UninstallDisplayIcon={app}\BateriaBT.exe
LicenseFile=LICENSE

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "startup"; Description: "Iniciar com o Windows"

[Files]
Source: "dist\BateriaBT\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Bateria BT"; Filename: "{app}\BateriaBT.exe"
; mesmo atalho que a opção "Iniciar com o Windows" do painel cria e confere
Name: "{userstartup}\BateriaBT"; Filename: "{app}\BateriaBT.exe"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\BateriaBT.exe"; Description: "Abrir o Bateria BT"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; o app aberto prende os arquivos: fecha antes de apagar
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im BateriaBT.exe"; Flags: runhidden; RunOnceId: "FecharApp"

[UninstallDelete]
; o atalho pode ter sido criado pelo painel, não pelo instalador
Type: files; Name: "{userstartup}\BateriaBT.lnk"
