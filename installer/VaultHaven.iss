#ifndef BuildVersion
  #define BuildVersion "0.1.0"
#endif

[Setup]
AppId={{7C4E25F8-7F4A-4E4D-98EF-1C426C2EE5C1}
AppName=VaultHaven
AppVersion={#BuildVersion}
AppPublisher=Fozly Rabby
AppPublisherURL=https://github.com/Rabby-XQ
AppSupportURL=https://github.com/Rabby-XQ/Valulthaven/issues
AppUpdatesURL=https://github.com/Rabby-XQ/Valulthaven/releases/latest
SetupIconFile=..\app\assets\vaulthaven.ico
DefaultDirName={localappdata}\Programs\VaultHaven
DefaultGroupName=VaultHaven
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
InfoBeforeFile=VaultHaven-Privacy-Policy.txt
InfoAfterFile=VaultHaven-After-Install.txt
UninstallDisplayName=VaultHaven
UninstallDisplayIcon={app}\VaultHaven.exe
CloseApplications=yes
CloseApplicationsFilter=VaultHaven.exe
RestartApplications=no
OutputDir=..\dist\installer
OutputBaseFilename=VaultHaven-Setup-{#BuildVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\VaultHaven\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "VaultHaven-Privacy-Policy.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "Third-Party-Notices.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\licenses"; DestName: "VaultHaven-MIT-LICENSE.txt"; Flags: ignoreversion
Source: "..\dist\Third-Party-Python-Licenses.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\dist\LGPL-3.0.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\dist\GPL-3.0.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\dist\Python-Runtime-LICENSE.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

; Remove documents installed at the program root by earlier VaultHaven builds.
[InstallDelete]
; Replace the complete frozen runtime on upgrades so Qt/PySide DLLs from an
; earlier build cannot remain beside the current runtime and be loaded instead.
; User backup data is stored separately under %LOCALAPPDATA%\VaultHaven\data.
Type: filesandordirs; Name: "{app}\_internal"
; Recreate the app-owned license directory from the current installer payload.
Type: filesandordirs; Name: "{app}\licenses"
; Older PyInstaller layouts placed runtime DLLs and Python modules beside the
; EXE. Remove those obsolete root-level files so Windows cannot load stale Qt
; or Python binaries ahead of the current runtime in _internal.
Type: files; Name: "{app}\*.dll"
Type: files; Name: "{app}\*.pyd"
Type: files; Name: "{app}\*.zip"
Type: filesandordirs; Name: "{app}\PySide6"
Type: filesandordirs; Name: "{app}\shiboken6"
Type: filesandordirs; Name: "{app}\telethon"
Type: filesandordirs; Name: "{app}\qasync"
Type: filesandordirs; Name: "{app}\cryptg"
Type: filesandordirs; Name: "{app}\app"
Type: files; Name: "{app}\VaultHaven-Privacy-Policy.txt"
Type: files; Name: "{app}\Third-Party-Notices.txt"
Type: files; Name: "{app}\VaultHaven-MIT-LICENSE.txt"
Type: files; Name: "{app}\Third-Party-Python-Licenses.txt"
Type: files; Name: "{app}\LGPL-3.0.txt"
Type: files; Name: "{app}\GPL-3.0.txt"
Type: files; Name: "{app}\Python-Runtime-LICENSE.txt"

[Icons]
Name: "{group}\VaultHaven"; Filename: "{app}\VaultHaven.exe"
Name: "{group}\Licenses\Privacy Policy"; Filename: "{app}\licenses\VaultHaven-Privacy-Policy.txt"
Name: "{group}\Licenses\Third-Party Notices"; Filename: "{app}\licenses\Third-Party-Notices.txt"
Name: "{group}\Licenses\VaultHaven MIT License"; Filename: "{app}\licenses\VaultHaven-MIT-LICENSE.txt"
Name: "{group}\Licenses\Third-Party Python Licenses"; Filename: "{app}\licenses\Third-Party-Python-Licenses.txt"
Name: "{group}\Licenses\Python Runtime License"; Filename: "{app}\licenses\Python-Runtime-LICENSE.txt"
Name: "{autodesktop}\VaultHaven"; Filename: "{app}\VaultHaven.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VaultHaven.exe"; Description: "Launch VaultHaven"; Flags: postinstall nowait skipifsilent

[Code]
function IsVaultHavenUpdate: Boolean;
begin
  Result := ExpandConstant('{param:VAULTHAVENUPDATE|0}') = '1';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and IsVaultHavenUpdate then
    Exec(ExpandConstant('{app}\VaultHaven.exe'), '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
end;

// User data under %LOCALAPPDATA% and Qt user settings are intentionally kept
// after uninstall, so removing the app cannot silently erase backup history.
