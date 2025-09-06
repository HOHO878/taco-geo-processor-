; Inno Setup Script for Survey Data Converter (64-bit)
; Corrected by Cline - AI Software Engineer

[Setup]
; --- معلومات التطبيق الأساسية ---
AppName=Survey Data Converter
AppVersion=1.0
AppPublisher=Mahmoud Kamal
AppPublisherURL=https://www.facebook.com/
AppSupportURL=https://www.facebook.com/
AppUpdatesURL=https://www.facebook.com/
AppId={{A7C1F8A0-9F2B-4B1C-8F0E-2A8C4D9B7E1D}

; --- إعدادات التثبيت ---
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\taco.exe
ArchitecturesAllowed=x64compatible
DefaultDirName={autopf64}\Survey Data Converter
DefaultGroupName=Survey Data Converter
DisableDirPage=no
DisableProgramGroupPage=no
OutputDir=.\installer
OutputBaseFilename=SurveyDataConverter_Setup_v1.0_x64
SetupIconFile=icons\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; --- التجربة البصرية والملفات ---
WizardImageFile=banners\welcome_banner.bmp
WizardSmallImageFile=banners\small_icon.bmp
LicenseFile=license.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; --- نسخ الملفات التنفيذية والتابعة لها ---
; ملاحظة: قبل تشغيل هذا السكريبت، يجب تشغيل أمر PyInstaller.
Source: "dist\taco64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; --- أيقونات قائمة ابدأ ---
; Explicitly use the first icon resource from the executable
Name: "{group}\Survey Data Converter"; Filename: "{app}\taco.exe"; IconIndex: 0
Name: "{group}\{cm:UninstallProgram,Survey Data Converter}"; Filename: "{uninstallexe}"

; --- أيقونة سطح المكتب (اختيارية) ---
; Explicitly use the first icon resource from the executable
Name: "{autodesktop}\Survey Data Converter"; Filename: "{app}\taco.exe"; Tasks: desktopicon; IconIndex: 0

[Run]
; --- تشغيل التطبيق بعد التثبيت ---
Filename: "{app}\taco.exe"; Description: "{cm:LaunchProgram,Survey Data Converter}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
english.FinishedLabel=Setup has finished installing %100 on your computer.
arabic.FinishedLabel=اكتمل التثبيت بنسبة 100%

; --- قسم التوقيع الرقمي (اختياري ولكنه موصى به بشدة) ---
; [Setup]
; SignTool=signtool.exe sign /f "C:\path\to\your\certificate.pfx" /p "your_password" /t http://timestamp.comodoca.com/authenticode $f
