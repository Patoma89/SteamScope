; =======================================================
; Script de Instalación Profesional - SteamScope 3.0 NEXT
; Desarrollado por Patoma89
; =======================================================

#define MyAppName "SteamScope"
#define MyAppVersion "3.0.0"
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
DirExistsWarning=no
DefaultGroupName={#MyAppName}
UsePreviousGroup=yes
DisableProgramGroupPage=auto
AllowNoIcons=yes
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
AppMutex=Patoma89_SteamScope_Mutex

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

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "icono.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "web_ui\*"; DestDir: "{app}\web_ui"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icono.ico"; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar SteamScope 3.0 NEXT al finalizar"; Flags: nowait postinstall

[Code]
// Limpieza real (NULL) de variables heredadas de PyInstaller 5/6
function SetEnvironmentVariableNull(lpName: String; lpValue: LongWord): Boolean;
external 'SetEnvironmentVariableW@kernel32.dll stdcall';

procedure ClearPyInstallerEnv();
begin
  SetEnvironmentVariableNull('_PYI_APPLICATION_HOME_DIR', 0);
  SetEnvironmentVariableNull('_PYI_ARCHIVE_FILE', 0);
  SetEnvironmentVariableNull('_PYI_PARENT_PROCESS_LEVEL', 0);
  SetEnvironmentVariableNull('_PYI_SPLASH_IPC', 0);
  SetEnvironmentVariableNull('_MEIPASS2', 0);
  SetEnvironmentVariableNull('_MEIPASS', 0);
  SetEnvironmentVariableNull('TCL_LIBRARY', 0);
  SetEnvironmentVariableNull('TK_LIBRARY', 0);
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

function ReadUninstallEntry(const RootKey: Integer; const KeySuffix: String; var InstallDir: String; var UninstExe: String): Boolean;
var
  SubKey, RawDir, RawUninst: String;
begin
  Result := False;
  InstallDir := '';
  UninstExe := '';
  SubKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + KeySuffix;
  if not RegKeyExists(RootKey, SubKey) then
    Exit;

  if RegQueryStringValue(RootKey, SubKey, 'Inno Setup: App Path', RawDir) or
     RegQueryStringValue(RootKey, SubKey, 'InstallLocation', RawDir) then
  begin
    RawDir := RemoveBackslashUnlessRoot(Trim(RemoveQuotes(RawDir)));
    if (RawDir <> '') and (not IsInsideTempPath(RawDir)) and DirExists(RawDir) then
      InstallDir := RawDir;
  end;

  if RegQueryStringValue(RootKey, SubKey, 'UninstallString', RawUninst) or
     RegQueryStringValue(RootKey, SubKey, 'QuietUninstallString', RawUninst) then
  begin
    UninstExe := ExtractExePath(RawUninst);
  end;

  Result := (InstallDir <> '') or (UninstExe <> '');
end;

function FindExistingInstallDir(): String;
var
  AppIdKey, LegacyKey, DummyUninst, FoundDir, Candidate: String;
begin
  Result := '';
  AppIdKey := '{D37E88E4-7E4A-4A7B-943E-2A4F9F24A5D1}_is1';
  LegacyKey := 'SteamScope_is1';

  if IsAdminInstallMode then
  begin
    if ReadUninstallEntry(HKLM, AppIdKey, FoundDir, DummyUninst) and (FoundDir <> '') then begin Result := FoundDir; Exit; end;
    if ReadUninstallEntry(HKCU, AppIdKey, FoundDir, DummyUninst) and (FoundDir <> '') then begin Result := FoundDir; Exit; end;
    if ReadUninstallEntry(HKLM, LegacyKey, FoundDir, DummyUninst) and (FoundDir <> '') then begin Result := FoundDir; Exit; end;
    if ReadUninstallEntry(HKCU, LegacyKey, FoundDir, DummyUninst) and (FoundDir <> '') then begin Result := FoundDir; Exit; end;
  end
  else
  begin
    if ReadUninstallEntry(HKCU, AppIdKey, FoundDir, DummyUninst) and (FoundDir <> '') then begin Result := FoundDir; Exit; end;
    if ReadUninstallEntry(HKCU, LegacyKey, FoundDir, DummyUninst) and (FoundDir <> '') then begin Result := FoundDir; Exit; end;
    if ReadUninstallEntry(HKLM, AppIdKey, FoundDir, DummyUninst) and (FoundDir <> '') then
    begin
      if Pos(NormalizeDir(ExpandConstant('{commonpf}')), NormalizeDir(FoundDir)) <> 1 then
      begin
        Result := FoundDir;
        Exit;
      end;
    end;
    if ReadUninstallEntry(HKLM, LegacyKey, FoundDir, DummyUninst) and (FoundDir <> '') then
    begin
      if Pos(NormalizeDir(ExpandConstant('{commonpf}')), NormalizeDir(FoundDir)) <> 1 then
      begin
        Result := FoundDir;
        Exit;
      end;
    end;
  end;

  Candidate := ExpandConstant('{localappdata}\Programs\{#MyAppName}');
  if FileExists(Candidate + '\{#MyAppExeName}') then
  begin
    Result := Candidate;
    Exit;
  end;

  Candidate := ExpandConstant('{commonpf}\{#MyAppName}');
  if IsAdminInstallMode and FileExists(Candidate + '\{#MyAppExeName}') then
  begin
    Result := Candidate;
    Exit;
  end;
end;

function InitializeSetup(): Boolean;
begin
  ClearPyInstallerEnv();
  Result := True;
end;

procedure InitializeWizard();
var
  ExistingDir: String;
begin
  if IsInsideTempPath(WizardForm.DirEdit.Text) then
    WizardForm.DirEdit.Text := ExpandConstant('{autopf}\{#MyAppName}');

  ExistingDir := FindExistingInstallDir();
  if ExistingDir <> '' then
    WizardForm.DirEdit.Text := ExistingDir;
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

// Desinstalación silenciosa de versiones previas o del ámbito opuesto
procedure UninstallPriorEntry(const RootKey: Integer; const KeySuffix: String);
var
  SubKey, DummyDir, UninstExe: String;
  ResultCode: Integer;
begin
  SubKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + KeySuffix;
  if not ReadUninstallEntry(RootKey, KeySuffix, DummyDir, UninstExe) then
    Exit;

  if (UninstExe <> '') and FileExists(UninstExe) then
  begin
    Exec(UninstExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end
  else
  begin
    RegDeleteKeyIncludingSubkeys(RootKey, SubKey);
  end;
end;

// Cierre automático del proceso y limpieza antes de instalar
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  AppIdKey: String;
begin
  ClearPyInstallerEnv();

  // Esperar brevemente a que la instancia previa cierre sola y cerrar SOLO SteamScope.exe SIN /T
  // (NUNCA usar /T: si este instalador fue lanzado por SteamScope.exe, /T mataría al propio instalador)
  Sleep(800);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);

  UninstallPriorEntry(HKCU, 'SteamScope_is1');
  UninstallPriorEntry(HKLM, 'SteamScope_is1');

  AppIdKey := '{D37E88E4-7E4A-4A7B-943E-2A4F9F24A5D1}_is1';
  if IsAdminInstallMode then
    UninstallPriorEntry(HKCU, AppIdKey)
  else
    UninstallPriorEntry(HKLM, AppIdKey);

  Result := '';
end;
