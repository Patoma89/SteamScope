; =======================================================
; Script de Instalación Profesional Completo - SteamScope v3.0.1
; Desarrollado por Patoma89
; =======================================================

#define MyAppName "SteamScope"
#ifndef MyAppVersion
#define MyAppVersion "3.0.1"
#endif
#define MyAppPublisher "Patoma89"
#define MyAppURL "https://github.com/Patoma89/SteamScope"
#define MyAppExeName "SteamScope.exe"

[Setup]
; Identificador único de la app (mantiene persistencia en actualizaciones)
AppId={{D37E88E4-7E4A-4A7B-943E-2A4F9F24A5D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Forzar actualización sobre la misma carpeta sin duplicar
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

; Desinstalador limpio y único en Windows (sin duplicar en lista de apps)
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[InstallDelete]
; Limpiar ejecutables temporales o antiguos en la carpeta de destino
Type: files; Name: "{app}\SteamScope_*.exe"
Type: files; Name: "{app}\*.old"
Type: files; Name: "{app}\*.tmp"
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; Archivo ejecutable único generado por PyInstaller en modo --onefile
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "icono.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Accesos directos en el menú de inicio y escritorio (apuntando a WorkingDir)
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Opción para ejecutar la app al terminar la instalación (también al actualizar con /SILENT)
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar SteamScope al finalizar"; Flags: nowait postinstall

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

  // 1. Cerrar procesos activos de SteamScope para liberar archivos bloqueados
  Exec('taskkill.exe', '/F /IM SteamScope.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(600);

  // 2. Limpiar versiones antiguas que se hayan instalado con nombres o IDs previos
  DesinstalarVersionHeredada(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SteamScope_is1');
  DesinstalarVersionHeredada(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SteamScope_is1');

  Result := '';
end;
