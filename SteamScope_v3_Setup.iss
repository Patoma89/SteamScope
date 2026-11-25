; =======================================================
; Script de Instalación Profesional - SteamScope 3.0 NEXT
; Desarrollado por Patoma89
; =======================================================

#define MyAppName "SteamScope"
#define MyAppVersion "3.0.1"
#define MyAppPublisher "Patoma89"
#define MyAppURL "https://github.com/Patoma89/SteamScope"
#define MyAppExeName "SteamScope.exe"

[Setup]
; Identificador único compartido con v2.0.1 para actualizar sin duplicar entradas
AppId={{D37E88E4-7E4A-4A7B-943E-2A4F9F24A5D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Actualización limpia sobre la carpeta existente
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
UsePreviousAppDir=yes
DisableDirPage=auto
DefaultGroupName={#MyAppName}
UsePreviousGroup=yes
DisableProgramGroupPage=auto
AllowNoIcons=yes

; Configuración del instalador final
OutputDir=Output
OutputBaseFilename=SteamScope_v{#MyAppVersion}_Setup
SetupIconFile=icono.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Desinstalador limpio y único en Windows
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[InstallDelete]
Type: files; Name: "{app}\SteamScope_*.exe"
Type: files; Name: "{app}\*.old"
Type: files; Name: "{app}\*.tmp"
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "icono.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar SteamScope 3.0 NEXT al finalizar"; Flags: nowait postinstall

[Code]
// Limpieza de variables de entorno heredadas de PyInstaller (_MEIPASS2 / _PYI_*)
function DeleteEnvironmentVariable(lpName: String; lpValue: NativeInt): Boolean;
external 'SetEnvironmentVariableW@kernel32.dll stdcall';

procedure LimpiarEntornoPyInstaller();
begin
  DeleteEnvironmentVariable('_MEIPASS', 0);
  DeleteEnvironmentVariable('_MEIPASS2', 0);
  DeleteEnvironmentVariable('_PYI_APPLICATION_HOME_DIR', 0);
  DeleteEnvironmentVariable('_PYI_ARCHIVE_FILE', 0);
  DeleteEnvironmentVariable('_PYI_PARENT_PROCESS_LEVEL', 0);
  DeleteEnvironmentVariable('_PYI_SPLASH_IPC', 0);
  DeleteEnvironmentVariable('PYTHONHOME', 0);
  DeleteEnvironmentVariable('PYTHONPATH', 0);
end;

function InitializeSetup(): Boolean;
begin
  LimpiarEntornoPyInstaller();
  Result := True;
end;

// Desinstalación silenciosa de versiones heredadas que usaban el AppId antiguo
procedure DesinstalarVersionHeredada(RootKey: Integer; SubKey: String);
var
  UninstCmd: String;
  ResultCode: Integer;
begin
  if RegQueryStringValue(RootKey, SubKey, 'QuietUninstallString', UninstCmd) or
     RegQueryStringValue(RootKey, SubKey, 'UninstallString', UninstCmd) then
  begin
    UninstCmd := RemoveQuotes(UninstCmd);
    if FileExists(UninstCmd) then
    begin
      Exec(UninstCmd, '/SILENT /VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;

// Cierre automático del proceso y limpieza antes de instalar
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  LimpiarEntornoPyInstaller();

  Exec('taskkill.exe', '/F /IM SteamScope.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(600);

  DesinstalarVersionHeredada(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SteamScope_is1');
  DesinstalarVersionHeredada(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SteamScope_is1');

  Result := '';
end;
