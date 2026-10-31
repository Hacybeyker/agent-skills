# Seguridad móvil

Supón que el binario será decompilado y el tráfico interceptado. Aunque alguien haga ingeniería inversa de la app, no debe obtener claves, secretos ni datos sensibles. La referencia es **[OWASP MASVS](https://mas.owasp.org/MASVS/)** (requisitos) y **MASTG** (cómo verificarlos). La seguridad se aplica desde el primer commit, no al final.

## 1. Secretos

- **Prohibido** escribir API keys, tokens, contraseñas o URLs sensibles en el código, en recursos o en `strings.xml`. Se extraen del binario en segundos.
- Los valores de configuración van en `local.properties` (fuera del repo) o en variables de entorno de CI, y se inyectan en el build: `BuildConfig` en Android, BuildKonfig en KMP.
- Eso **dificulta** la extracción pero no la impide: el valor sigue dentro del binario. Para secretos críticos, la mejor opción es que **nunca viajen en la app**: el backend actúa de proxy y protege el endpoint con la autenticación del usuario.
- `gitleaks` (o similar) en CI para detectar secretos antes de que lleguen al repo.

## 2. Red

- **Solo HTTPS.** Ningún `http://`, ni en debug contra servicios reales.
- Android: `networkSecurityConfig` con `cleartextTrafficPermitted="false"`. iOS: App Transport Security sin excepciones globales.
- **Certificate pinning** en apps con datos sensibles, siempre con **al menos un pin de respaldo** para poder rotar certificados:

```kotlin
// Android (OkHttp, o Ktor con motor OkHttp)
val pinner = CertificatePinner.Builder()
    .add("api.midominio.com", "sha256/<pin-actual>")
    .add("api.midominio.com", "sha256/<pin-de-respaldo>")
    .build()
```
  En iOS con Ktor (motor Darwin), usa el `CertificatePinner` del motor Darwin.
- Nunca desactives la validación TLS (`trustAll`), ni en builds que lleguen a testers.
- Ningún log de cuerpos de solicitud o respuesta en release.

## 3. Almacenamiento

| Dato | Dónde |
| --- | --- |
| Tokens, credenciales, claves | Android: **Keystore**. iOS: **Keychain** (`kSecAttrAccessibleWhenUnlockedThisDeviceOnly`). En KMP, detrás de una interfaz `SecureStorage` con implementación por plataforma |
| Datos estructurados sensibles | Room + SQLCipher (con la clave custodiada por Keystore/Keychain), o campos cifrados antes de guardarlos |
| Preferencias no sensibles | DataStore sin cifrar |

- Cifrado simétrico **AES-256-GCM**. En Android usa **Tink** (la librería criptográfica de Google) con su clave maestra en el Keystore. No implementes criptografía propia.
- Claves de datos de alto valor con autenticación del usuario (`setUserAuthenticationRequired` + `androidx.biometric`; en iOS, `LAContext`).
- Excluye datos sensibles de los backups: Android con `dataExtractionRules` / `fullBackupContent` (o `allowBackup="false"`); iOS con `isExcludedFromBackup`.
- Borra tokens y datos sensibles al cerrar sesión.

## 4. Binario

**Android (R8):**
- Minificación y reducción de recursos en todo build de release (modo completo de R8, [performance.md](performance.md)).
- Reglas `-keep` mínimas: cada una deja código sin ofuscar. Las librerías (kotlinx.serialization, Room, Hilt) traen las suyas.
- El `mapping.txt` se sube al servicio de crashes, nunca al repo.

**iOS (Kotlin/Native):**
- Minimiza la API pública del framework compartido: `internal` por defecto, `explicitApi()` en los módulos de librería.
- Release optimizado y sin símbolos de debug en el binario distribuido (dSYM aparte para los crashes).

## 5. Higiene en runtime

- Ningún log con tokens, datos personales o cuerpos de red en release. Usa un logger que se apague por tipo de build.
- Ningún dato sensible en mensajes de error, analytics ni reportes de crash.
- Pantallas sensibles: oculta el contenido en el selector de apps y bloquea capturas (`FLAG_SECURE` en Android).
- **Deep links:** valida y sanea los parámetros. Nunca permitas saltar la autenticación ni llegar a pantallas privilegiadas desde un enlace.
- **WebViews:** JavaScript desactivado si no hace falta, solo URLs propias, y ningún `addJavascriptInterface` sin validación.
- Android: `android:exported="false"` por defecto en Activities, Services y Receivers que no necesiten ser públicos.

## 6. Defensas adicionales (apps de alto valor: fintech, salud)

- **Integridad de la app:** Play Integrity API (Android) y App Attest (iOS), verificados en el backend.
- Detección de root/jailbreak, debugger y hooking (Frida): es disuasión, no garantía. Degrada funciones o avisa al backend.
- RASP o *app shielding* comercial (por ejemplo DexGuard/iXGuard) si el negocio lo justifica.

## Checklist antes de cada release

- [ ] Cero secretos en código y recursos (busca `apiKey`, `password`, `secret`, `token`).
- [ ] Solo HTTPS; pinning con pin de respaldo donde aplica.
- [ ] Tokens y credenciales en Keystore/Keychain, nunca en texto plano.
- [ ] R8 activo en release y reglas `-keep` justificadas.
- [ ] Logs de red y de debug apagados en release.
- [ ] Deep links y WebViews validados; componentes no exportados por defecto.
- [ ] Backups sin datos sensibles.
- [ ] Release decompilado (jadx) para verificar que no se lee nada sensible.
