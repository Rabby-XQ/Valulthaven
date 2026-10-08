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
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
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

; User data under %LOCALAPPDATA% and Qt user settings are intentionally kept
; after uninstall, so removing the app cannot silently erase backup history.
