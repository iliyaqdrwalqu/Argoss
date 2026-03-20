; Inno Setup script — ARGOS Absolute Windows Installer
; Build: ISCC.exe installer\argos_setup.iss
; Output: installer\Output\ARGOS_Setup.exe

#define AppName      "ARGOS Absolute"
#define AppVersion   "1.33.0"
#define AppPublisher "sigtrip"
#define AppURL       "https://github.com/iliyaqdrwalqu/Argoss"
#define AppExeName   "ARGOS.exe"
; PyInstaller outputs the exe one directory above this script
#define DistDir      "..\dist"

[Setup]
AppId={{A3B5C7D9-1E2F-4A6B-8C0D-E1F2A3B4C5D6}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=ARGOS_Setup
Compression=lzma2/ultra64
SolidCompression=yes
; Minimum Windows 10
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
; Allow non-admin install into user profile
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "russian";    MessagesFile: "compiler:Languages\Russian.isl"
Name: "english";    MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main executable built by PyInstaller
Source: "{#DistDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";                  Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";            Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
