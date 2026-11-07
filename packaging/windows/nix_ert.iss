; Inno Setup script for the NiX ERT desktop application (Windows, 64-bit).
;
; Per-user install (PrivilegesRequired=lowest): everything lands under
; %LOCALAPPDATA%\Programs\NiX ERT, so no administrator prompt is needed and no
; machine-wide state is touched. The uninstaller is registered under HKCU.
;
; Build it through tools/build_windows_installer.py, which passes MyAppVersion
; and BundleDir so this script never carries a second copy of either.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef BundleDir
  #define BundleDir "..\..\dist\NiX ERT"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\installer"
#endif

#define MyAppName "NiX ERT"
#define MyAppPublisher "NiX ERT contributors"
#define MyAppExeName "NiX ERT.exe"

[Setup]
AppId={{7E1B9D2C-4C4A-4C0B-9C41-7A5E2F6B8D10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=NiX-ERT-{#MyAppVersion}-win64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
