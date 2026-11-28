; Figma logical pixels, independent of the Windows display scale.
!define INSTALLER_WINDOW_SIZE 600
!define INSTALLER_BRAND_Y 98
!define INSTALLER_BRAND_HEIGHT 220
!define INSTALLER_BUTTON_X 234
!define INSTALLER_BUTTON_Y 444
!define INSTALLER_BUTTON_WIDTH 132
!define INSTALLER_BUTTON_HEIGHT 48
!define INSTALLER_BUTTON_DIAMETER 14
!define INSTALLER_PROGRESS_X 64
!define INSTALLER_PROGRESS_Y 482
!define INSTALLER_PROGRESS_WIDTH 472
!define INSTALLER_PROGRESS_HEIGHT 6
!define INSTALLER_PROGRESS_DIAMETER 4
!define INSTALLER_STATUS_Y 548
!define INSTALLER_STATUS_HEIGHT 30
!define INSTALLER_FONT "Microsoft YaHei UI"
!define INSTALLER_BUTTON_FONT_SIZE 16
!define INSTALLER_STATUS_FONT_SIZE 14
; GDI+ ARGB values; GDI text uses COLORREF below.
!define INSTALLER_PRIMARY 0xFF14547F
!define INSTALLER_PRIMARY_HOVER 0xFF1B6497
!define INSTALLER_PRIMARY_PRESSED 0xFF0E4265
!define INSTALLER_CONTROL_HOVER 0xFFE6EDF2
!define INSTALLER_CONTROL_PRESSED 0xFFD9E3EA
!define INSTALLER_DARK_CONTROL_HOVER 0xFF2B3741
!define INSTALLER_DARK_CONTROL_PRESSED 0xFF3A4955
!define INSTALLER_TRACK_COLOR 0xFFDCE5EB
!define INSTALLER_TEXT_COLORREF 0x2D1F0D

Var InstallerTheme
Var InstallerBgHex
Var InstallerTextHex
Var InstallerBgArgb
Var InstallerBgColorref
Var InstallerTextColorref
Var InstallerPrimary
Var InstallerPrimaryHover
Var InstallerPrimaryPressed
Var InstallerControlHover
Var InstallerControlPressed
Var InstallerTrack
Var InstallerButtonText
Var InstallerBorder

; SetCtlColors accepts only compile-time colors; choose between the two native palettes.
!macro InstallerControlColors HANDLE
    ${If} $InstallerTheme == "dark"
        SetCtlColors ${HANDLE} F5F7FA 111820
    ${Else}
        SetCtlColors ${HANDLE} 0D1F2D F5F7FA
    ${EndIf}
!macroend

Function InstallerResolveTheme
    ${If} $InstallerTheme == "auto"
        ClearErrors
        ReadRegDWORD $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" "AppsUseLightTheme"
        ${If} ${Errors}
            StrCpy $0 1
        ${EndIf}
        ${If} $0 == 0
            StrCpy $InstallerTheme "dark"
        ${Else}
            StrCpy $InstallerTheme "light"
        ${EndIf}
    ${EndIf}
    ${If} $InstallerTheme == "dark"
        StrCpy $InstallerBgHex "111820"
        StrCpy $InstallerTextHex "F5F7FA"
        StrCpy $InstallerBgArgb 0xFF111820
        StrCpy $InstallerBgColorref 0x201811
        StrCpy $InstallerTextColorref 0xFAF7F5
        StrCpy $InstallerPrimary 0xFF2D79A3
        StrCpy $InstallerPrimaryHover 0xFF3D89B3
        StrCpy $InstallerPrimaryPressed 0xFF1B6497
        StrCpy $InstallerControlHover ${INSTALLER_DARK_CONTROL_HOVER}
        StrCpy $InstallerControlPressed ${INSTALLER_DARK_CONTROL_PRESSED}
        StrCpy $InstallerTrack 0xFF4A5965
        StrCpy $InstallerButtonText 0xFFFFFF
        StrCpy $InstallerBorder 0xFF4A5965
    ${Else}
        StrCpy $InstallerBgHex "F5F7FA"
        StrCpy $InstallerTextHex "0D1F2D"
        StrCpy $InstallerBgArgb 0xFFF5F7FA
        StrCpy $InstallerBgColorref 0xFAF7F5
        StrCpy $InstallerTextColorref ${INSTALLER_TEXT_COLORREF}
        StrCpy $InstallerPrimary ${INSTALLER_PRIMARY}
        StrCpy $InstallerPrimaryHover ${INSTALLER_PRIMARY_HOVER}
        StrCpy $InstallerPrimaryPressed ${INSTALLER_PRIMARY_PRESSED}
        StrCpy $InstallerControlHover ${INSTALLER_CONTROL_HOVER}
        StrCpy $InstallerControlPressed ${INSTALLER_CONTROL_PRESSED}
        StrCpy $InstallerTrack ${INSTALLER_TRACK_COLOR}
        StrCpy $InstallerButtonText 0xFFFFFF
        StrCpy $InstallerBorder 0xFFB8C7D2
    ${EndIf}
FunctionEnd
