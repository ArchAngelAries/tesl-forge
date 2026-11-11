; TESL Forge installer (Inno Setup 6). Built by tools/build_installer.py, which passes the version and folders:
;   ISCC /DAppVersion=x.y.z /DSourceDir=<PyInstaller app folder> /DOutDir=<output> tesl-forge.iss
; Installs for the current user (no administrator prompt) into %LOCALAPPDATA%\Programs\TESL Forge.
; Mods and the workspace live in Documents\TESL Forge and are never removed by the uninstaller.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1E0B53-8F43-4C35-9B61-2F3B8C7E5A10}
AppName=TESL Forge
AppVersion={#AppVersion}
AppVerName=TESL Forge {#AppVersion}
AppPublisher=ArchAngelAries
AppPublisherURL=https://ko-fi.com/archangelaries
AppSupportURL=https://www.patreon.com/c/ArchAngelAries
DefaultDirName={autopf}\TESL Forge
DefaultGroupName=TESL Forge
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutDir}
OutputBaseFilename=TESL-Forge-Setup-{#AppVersion}
SetupIconFile=..\..\tesl_suite\web\icon.ico
UninstallDisplayIcon={app}\TESL Forge.exe
UninstallDisplayName=TESL Forge
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
InfoBeforeFile=..\..\DISCLAIMER.md

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TESL Forge"; Filename: "{app}\TESL Forge.exe"; AppUserModelID: "ArchAngelAries.TESLForge"
Name: "{group}\Uninstall TESL Forge"; Filename: "{uninstallexe}"
Name: "{autodesktop}\TESL Forge"; Filename: "{app}\TESL Forge.exe"; Tasks: desktopicon; AppUserModelID: "ArchAngelAries.TESLForge"

[Run]
Filename: "{app}\TESL Forge.exe"; Description: "Open TESL Forge"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
