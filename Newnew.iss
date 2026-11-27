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
PrivilegesRequired=admin
DefaultDirName={autopf}\{#MyAppName}
UsePreviousAppDir=yes
DisableDirPage=auto
DefaultGroupName={#MyAppName}
UsePreviousGroup=yes
DisableProgramGroupPage=auto
UsePreviousTasks=yes
AllowNoIcons=yes
DirExistsWarning=no
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}

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

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Icons]
; Accesos directos en el menú de inicio y escritorio (apuntando a WorkingDir)
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Opción para ejecutar la app al terminar la instalación (también al actualizar con /SILENT)
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar SteamScope al finalizar"; Flags: nowait postinstall runasoriginaluser

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

function NormalizeDir(const S: String): String;
begin
  Result := LowerCase(RemoveBackslashUnlessRoot(Trim(RemoveQuotes(S))));
end;

function IsInsideTempPath(const DirPath: String): Boolean;
var
  NormDir, Temp1, Temp2: String;
begin
  Result := False;
  NormDir := NormalizeDir(DirPath);
  if NormDir = '' then
    Exit;
  Temp1 := NormalizeDir(GetTempDir());
  Temp2 := NormalizeDir(ExpandConstant('{localappdata}\Temp'));
  if (NormDir = Temp1) or (Pos(Temp1 + '\', NormDir) = 1) or
     (NormDir = Temp2) or (Pos(Temp2 + '\', NormDir) = 1) or
     (Pos('\appdata\local\temp\', NormDir + '\') > 0) then
    Result := True;
end;

function ExtractExePath(const Cmd: String): String;
var
  S: String;
  P: Integer;
begin
  S := Trim(Cmd);
  if S = '' then
  begin
    Result := '';
    Exit;
  end;
  if S[1] = '"' then
  begin
    Delete(S, 1, 1);
    P := Pos('"', S);
    if P > 0 then
      S := Copy(S, 1, P - 1);
  end
  else
  begin
    P := Pos('.exe', LowerCase(S));
    if P > 0 then
      S := Copy(S, 1, P + 3);
  end;
  Result := Trim(S);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if IsInsideTempPath(WizardDirValue) then
    begin
      MsgBox('No se puede instalar SteamScope dentro de la carpeta temporal (Temp). Elegí una carpeta permanente.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

// Desinstalación silenciosa de versiones heredadas o huérfanas
procedure DesinstalarVersionHeredada(RootKey: Integer; SubKey: String);
var
  UninstCmd, UninstExe: String;
  ResultCode: Integer;
begin
  if not RegKeyExists(RootKey, SubKey) then
    Exit;

  if RegQueryStringValue(RootKey, SubKey, 'UninstallString', UninstCmd) or
     RegQueryStringValue(RootKey, SubKey, 'QuietUninstallString', UninstCmd) then
  begin
    UninstExe := ExtractExePath(UninstCmd);
    if (UninstExe <> '') and FileExists(UninstExe) then
    begin
      Exec(UninstExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end
    else
    begin
      RegDeleteKeyIncludingSubkeys(RootKey, SubKey);
    end;
  end;
end;

// Limpia restos per-user de v2.0.1 y accesos directos obsoletos para evitar bucles
procedure LimpiarInstalacionPerUserResidual();
var
  PerUserDir, TargetDir, UserDesktopLnk, UserGroupDir: String;
begin
  PerUserDir := ExpandConstant('{localappdata}\Programs\{#MyAppName}');
  TargetDir := ExpandConstant('{app}');
  if (NormalizeDir(PerUserDir) <> NormalizeDir(TargetDir)) and
     DirExists(PerUserDir) and FileExists(PerUserDir + '\{#MyAppExeName}') then
  begin
    DelTree(PerUserDir, True, True, True);
  end;

  UserDesktopLnk := ExpandConstant('{userdesktop}\{#MyAppName}.lnk');
  if (NormalizeDir(ExpandConstant('{userdesktop}')) <> NormalizeDir(ExpandConstant('{autodesktop}'))) and
     FileExists(UserDesktopLnk) then
  begin
    DeleteFile(UserDesktopLnk);
  end;

  UserGroupDir := ExpandConstant('{userprograms}\{#MyAppName}');
  if (NormalizeDir(UserGroupDir) <> NormalizeDir(ExpandConstant('{group}'))) and
     DirExists(UserGroupDir) then
  begin
    DelTree(UserGroupDir, True, True, True);
  end;
end;

// Cierre automático del proceso y limpieza antes de instalar
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  LimpiarEntornoPyInstaller();

  // Esperar brevemente a que SteamScope cierre solo y cerrar sin /T para no matar este instalador
  Sleep(500);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);

  // Limpiar versiones antiguas que se hayan instalado con nombres o IDs previos
  DesinstalarVersionHeredada(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SteamScope_is1');
  DesinstalarVersionHeredada(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SteamScope_is1');
  DesinstalarVersionHeredada(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{D37E88E4-7E4A-4A7B-943E-2A4F9F24A5D1}_is1');
  LimpiarInstalacionPerUserResidual();

  Result := '';
end;
