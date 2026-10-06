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
DefaultDirName={localappdata}\Programs\VaultHaven
DefaultGroupName=VaultHaven
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
LicenseFile=VaultHaven-EULA.txt
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
Source: "VaultHaven-Privacy-Policy.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "VaultHaven-EULA.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "Third-Party-Notices.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VaultHaven"; Filename: "{app}\VaultHaven.exe"
Name: "{group}\Privacy Policy"; Filename: "{app}\VaultHaven-Privacy-Policy.txt"
Name: "{group}\Third-Party Notices"; Filename: "{app}\Third-Party-Notices.txt"
Name: "{autodesktop}\VaultHaven"; Filename: "{app}\VaultHaven.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VaultHaven.exe"; Description: "Launch VaultHaven"; Flags: postinstall nowait skipifsilent

; User data under %LOCALAPPDATA% and Qt user settings are intentionally kept
; after uninstall, so removing the app cannot silently erase backup history.
