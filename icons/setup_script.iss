
[Setup]
AppName=Survey Data Converter
AppVersion=1.0
DefaultDirName={pf}\SurveyDataConverter
DefaultGroupName=SurveyDataConverter
OutputDir=.
OutputBaseFilename=SurveyDataConverter_Setup
SetupIconFile=icons\app_icon.ico
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\taco.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "banners\welcome_banner.bmp"; DestDir: "{app}\banners"; Flags: ignoreversion
Source: "banners\small_icon.bmp"; DestDir: "{app}\banners"; Flags: ignoreversion
Source: "icons\app_icon.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "license.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SurveyDataConverter"; Filename: "{app}\taco.exe"

[Run]
Filename: "{app}\taco.exe"; Description: "Launch Survey Data Converter"; Flags: nowait postinstall skipifsilent
