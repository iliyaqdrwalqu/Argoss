
; ════════════════════════════════════════════════════════════
;  ARGOS UNIVERSAL OS — Windows Installer (NSIS)
;  Создан автоматически setup_builder.py
; ════════════════════════════════════════════════════════════

!define APP_NAME      "Argos Universal OS"
!define APP_VERSION   "1.0.0"
!define APP_EXE       "argos.exe"
!define INSTALL_DIR   "$PROGRAMFILES64\ArgosUniversalOS"
!define REG_KEY       "Software\Microsoft\Windows\CurrentVersion\Uninstall\ArgosUniversalOS"

; Метаданные
Name              "${APP_NAME} ${APP_VERSION}"
OutFile           "setup_argos.exe"
InstallDir        "${INSTALL_DIR}"
InstallDirRegKey  HKLM "${REG_KEY}" "InstallLocation"
RequestExecutionLevel admin    ; <-- ТРЕБУЕТ ПРАВА АДМИНИСТРАТОРА

; Современный интерфейс
!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "assets\argos_icon.ico"
!define MUI_UNICON "assets\argos_icon.ico"
!define MUI_HEADERIMAGE
!define MUI_BGCOLOR "060A1A"
!define MUI_TEXTCOLOR "00FFFF"

; Страницы установки
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Страницы удаления
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "English"

; ════════════════════════════════════════════════════════════
Section "Argos Core" SecCore
    SectionIn RO    ; Обязательная секция

    SetOutPath "${INSTALL_DIR}"
    File /r "dist\argos\*.*"

    ; Копируем конфиги
    SetOutPath "${INSTALL_DIR}\config"
    File /nonfatal "config\identity.json"

    ; Создаём .env если нет
    IfFileExists "${INSTALL_DIR}\.env" env_exists
        FileOpen  $0 "${INSTALL_DIR}\.env" w
        FileWrite $0 "GEMINI_API_KEY=your_key_here$\r$\n"
        FileWrite $0 "TELEGRAM_BOT_TOKEN=your_token_here$\r$\n"
        FileWrite $0 "USER_ID=your_telegram_id$\r$\n"
        FileClose $0
    env_exists:

    ; Запись в реестр
    WriteRegStr   HKLM "${REG_KEY}" "DisplayName"     "${APP_NAME}"
    WriteRegStr   HKLM "${REG_KEY}" "DisplayVersion"   "${APP_VERSION}"
    WriteRegStr   HKLM "${REG_KEY}" "Publisher"        "Vsevolod / Argos Project"
    WriteRegStr   HKLM "${REG_KEY}" "InstallLocation"  "${INSTALL_DIR}"
    WriteRegStr   HKLM "${REG_KEY}" "UninstallString"  '"${INSTALL_DIR}\uninstall.exe"'
    WriteRegDWORD HKLM "${REG_KEY}" "NoModify"         1
    WriteRegDWORD HKLM "${REG_KEY}" "NoRepair"         1

    ; Создаём деинсталлятор
    WriteUninstaller "${INSTALL_DIR}\uninstall.exe"
SectionEnd

; ════════════════════════════════════════════════════════════
Section "Ярлыки" SecShortcuts
    ; Рабочий стол
    CreateShortcut "$DESKTOP\Argos Universal OS.lnk" \
        "${INSTALL_DIR}\${APP_EXE}" "" \
        "${INSTALL_DIR}\${APP_EXE}" 0

    ; Меню Пуск
    CreateDirectory "$SMPROGRAMS\Argos Universal OS"
    CreateShortcut  "$SMPROGRAMS\Argos Universal OS\Argos.lnk" \
        "${INSTALL_DIR}\${APP_EXE}"
    CreateShortcut  "$SMPROGRAMS\Argos Universal OS\Удалить.lnk" \
        "${INSTALL_DIR}\uninstall.exe"
SectionEnd

; ════════════════════════════════════════════════════════════
Section "Автозапуск (Системный сервис)" SecService
    ; Регистрируем argos как Windows Service через NSSM
    ; (Non-Sucking Service Manager — скачивается автоматически)
    nsExec::ExecToLog '"${INSTALL_DIR}\nssm.exe" install ArgosService "${INSTALL_DIR}\${APP_EXE}" "--no-gui"'
    nsExec::ExecToLog '"${INSTALL_DIR}\nssm.exe" set ArgosService DisplayName "Argos Universal OS Service"'
    nsExec::ExecToLog '"${INSTALL_DIR}\nssm.exe" set ArgosService Description "Всевидящий ИИ-сервис Аргос"'
    nsExec::ExecToLog '"${INSTALL_DIR}\nssm.exe" set ArgosService Start SERVICE_AUTO_START'
    nsExec::ExecToLog '"${INSTALL_DIR}\nssm.exe" start ArgosService'

    ; Запись в автозапуск реестра (дублирование)
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Run" \
        "ArgosUniversalOS" '"${INSTALL_DIR}\${APP_EXE}"'
SectionEnd

; ════════════════════════════════════════════════════════════
Section "Uninstall"
    ; Останавливаем сервис
    nsExec::ExecToLog '"$INSTDIR\nssm.exe" stop ArgosService'
    nsExec::ExecToLog '"$INSTDIR\nssm.exe" remove ArgosService confirm'

    ; Убираем из автозапуска
    DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "ArgosUniversalOS"

    ; Удаляем файлы
    RMDir /r "$INSTDIR"
    Delete   "$DESKTOP\Argos Universal OS.lnk"
    RMDir /r "$SMPROGRAMS\Argos Universal OS"

    ; Удаляем из реестра
    DeleteRegKey HKLM "${REG_KEY}"
SectionEnd
