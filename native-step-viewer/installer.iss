[Setup]
AppId={{A98F5167-09D9-4E0B-846D-85793FC02F8C}
AppName=CapsuleDesign STEP Viewer
AppVersion=0.3.2
AppPublisher=INITIALTEC
DefaultDirName={localappdata}\Programs\CapsuleDesign STEP Viewer
DefaultGroupName=CapsuleDesign STEP Viewer
OutputDir=dist
OutputBaseFilename=CapsuleDesign_STEPViewer_Setup_v0.3.2
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=CapsuleDesign STEP Viewer
DisableProgramGroupPage=yes

[Files]
Source: "dist\CapsuleSTEPViewer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\CapsuleDesign STEP Viewer"; Filename: "{app}\CapsuleSTEPViewer.exe"; WorkingDir: "{app}"
Name: "{userprograms}\CapsuleDesign STEP Viewer"; Filename: "{app}\CapsuleSTEPViewer.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\CapsuleSTEPViewer.exe"; Description: "CapsuleDesign STEP Viewer 실행"; Flags: nowait postinstall skipifsilent
