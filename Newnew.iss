; =======================================================
; Script de Instalación Profesional Completo - SteamScope v2.0.1
; Desarrollado por Patoma89
; =======================================================

#define MyAppName "SteamScope"
#define MyAppVersion "2.0.1"
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

; Permite elegir la ruta de instalación de forma interactiva
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Configuración del instalador final
OutputDir=Output
OutputBaseFilename=SteamScope_v{#MyAppVersion}_Setup
SetupIconFile=icono.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Desinstalador limpio
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} v{#MyAppVersion}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
; Archivo ejecutable único generado por PyInstaller en modo --onefile
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "icono.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Accesos directos en el menú de inicio y escritorio (usando {userdesktop} compatible sin admin)
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Opción para ejecutar la app al terminar la instalación (también al actualizar con /SILENT)
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar SteamScope al finalizar"; Flags: nowait postinstall

[Code]
// Limpieza de variables de entorno heredadas de PyInstaller (_MEIPASS2)
// para evitar el diálogo "Failed to load Python DLL" al reiniciar
function SetEnvironmentVariable(lpName: String; lpValue: String): Boolean;
external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function InitializeSetup(): Boolean;
begin
  SetEnvironmentVariable('_MEIPASS2', '');
  SetEnvironmentVariable('_MEIPASS', '');
  Result := True;
end;

// Cierre automático del proceso en caso de actualización con la app abierta
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  SetEnvironmentVariable('_MEIPASS2', '');
  SetEnvironmentVariable('_MEIPASS', '');
  Exec('taskkill.exe', '/F /IM SteamScope.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
