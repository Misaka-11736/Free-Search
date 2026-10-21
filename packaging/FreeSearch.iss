#ifndef StagingDir
  #define StagingDir "..\dist\installer-stage\FreeSearch"
#endif
#ifndef SetupOutput
  #define SetupOutput "..\dist\installer-release"
#endif

[Setup]
AppId={{73855F98-1929-4473-90DA-2E79506FBF0C}
AppName=Free Search
AppVersion=0.1.0
AppVerName=Free Search 0.1.0-preview
AppPublisher=Free Search contributors
AppPublisherURL=https://github.com/Misaka-11736/Free-Search
AppSupportURL=https://github.com/Misaka-11736/Free-Search/issues
AppUpdatesURL=https://github.com/Misaka-11736/Free-Search/releases
DefaultDirName={localappdata}\Programs\FreeSearch
DefaultGroupName=Free Search
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
DisableProgramGroupPage=yes
InfoBeforeFile={#StagingDir}\BINARY_LICENSE.txt
OutputDir={#SetupOutput}
OutputBaseFilename=FreeSearch-Setup-0.1.0-preview
Compression=lzma2/fast
SolidCompression=yes
DiskSpanning=yes
DiskSliceSize=1800000000
SlicesPerDisk=1
WizardStyle=modern
UninstallDisplayName=Free Search 0.1.0-preview
UninstallDisplayIcon={app}\FreeSearch-offline.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建完全离线版桌面快捷方式 / Create offline desktop shortcut"; GroupDescription: "快捷方式 / Shortcuts:"

[Files]
Source: "{#StagingDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Free Search - 完全离线版"; Filename: "{app}\FreeSearch-offline.exe"; WorkingDir: "{app}"
Name: "{group}\Free Search - API 版"; Filename: "{app}\FreeSearch-api.exe"; WorkingDir: "{app}"
Name: "{group}\卸载 Free Search"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Free Search - 完全离线版"; Filename: "{app}\FreeSearch-offline.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FreeSearch-offline.exe"; Description: "启动 Free Search 完全离线版 / Launch offline edition"; Flags: nowait postinstall skipifsilent
