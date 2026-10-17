; Inno Setup script for TabloView. Built by packaging/build.ps1 (pass /DAppVersion=x.y.z).
; Per-user install: no admin rights needed, installs to %LOCALAPPDATA%\Programs\TabloView.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6F2C8E14-3B7A-4D61-9C2E-7A1B5D0E4F93}
AppName=TabloView
AppVersion={#AppVersion}
AppVerName=TabloView {#AppVersion}
AppPublisher=Joe Del Vecchio
DefaultDirName={localappdata}\Programs\TabloView
DefaultGroupName=TabloView
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TabloView-Setup-{#AppVersion}
SetupIconFile=..\build\stage\tabloview.ico
UninstallDisplayIcon={app}\TabloView.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start TabloView when I sign in to Windows"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\TabloView\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TabloView"; Filename: "{app}\TabloView.exe"
Name: "{group}\Uninstall TabloView"; Filename: "{uninstallexe}"
Name: "{userdesktop}\TabloView"; Filename: "{app}\TabloView.exe"; Tasks: desktopicon
Name: "{userstartup}\TabloView"; Filename: "{app}\TabloView.exe"; Tasks: startup

[Run]
Filename: "{app}\TabloView.exe"; Description: "Open TabloView now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop a running copy so its files can be removed
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im TabloView.exe"; Flags: runhidden; RunOnceId: "StopTabloView"

[UninstallDelete]
; Keep the user's sign-in and settings in %LOCALAPPDATA%\TabloView unless they delete it themselves;
; only clear temporary stream files.
Type: filesandordirs; Name: "{localappdata}\TabloView\transcode"
