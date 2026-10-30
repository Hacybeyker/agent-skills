# Dominio: seguridad de aplicaciones

Mapa para diseñar planes y enseñar seguridad en web, APIs y móvil. Para cifrado, claves y protocolos, combínalo con `dominio-criptografia.md`.

## Límites de la enseñanza

Enseña seguridad **defensiva**: cómo funciona una vulnerabilidad a nivel conceptual, cómo detectarla en el propio código y cómo corregirla o prevenirla. No generes exploits funcionales, malware ni instrucciones para atacar sistemas de terceros. Las prácticas ofensivas se limitan a entornos propios o autorizados y a laboratorios pensados para ello.

## Mapa de competencias

### 🟢 Básico
- Confidencialidad, integridad y disponibilidad; autenticación frente a autorización; mínimo privilegio; defensa en profundidad.
- Panorama del OWASP Top 10.
- Contraseñas: se guardan con hash lento y sal, nunca cifradas ni en claro.
- HTTPS y TLS a alto nivel.
- Validación de entrada y codificación de salida.
- Secretos fuera del repositorio; dependencias al día.

### 🟡 Intermedio
- **Inyección**: SQL, NoSQL y comandos; consultas parametrizadas.
- **Navegador**: XSS y CSP, CSRF y `SameSite`, CORS, cookies seguras, clickjacking.
- **Control de acceso**: IDOR/BOLA, autorización por recurso, multi-tenant.
- **Identidad**: sesiones, JWT bien usados, OAuth 2.0 y OpenID Connect (authorization code con PKCE, client credentials), MFA, passkeys (WebAuthn).
- **Móvil**: almacenamiento seguro (Keychain, Keystore), comunicaciones seguras, OWASP MASVS.
- **Operación**: logging sin datos sensibles, rate limiting, cabeceras de seguridad, SSRF.

### 🟠 Avanzado
- **Modelado de amenazas** (STRIDE, diagramas de flujo de datos, abuso de casos de uso).
- **Pruebas**: SAST, DAST, SCA, revisión de código segura, fuzzing.
- **Cadena de suministro**: lockfiles, SBOM, firmas, SLSA, seguridad de CI/CD.
- **Secretos**: gestores de secretos, rotación, credenciales de corta duración.
- **APIs**: OWASP API Security Top 10, mTLS, gateways.
- **Móvil avanzado**: certificate pinning y sus riesgos, Play Integrity y App Attest, ofuscación y hardening, detección de manipulación.
- **Privacidad**: minimización de datos, cifrado en reposo y en tránsito, principios de las normativas de protección de datos.

### 🔴 Experto
- Arquitecturas zero trust y diseño de sistemas de identidad.
- Respuesta a incidentes y análisis forense a alto nivel.
- Programas de seguridad: ASVS por niveles, security champions, bug bounty.
- Criptografía aplicada y gestión de claves a escala.

## Rutas típicas

- **Fundamentos de AppSec**: principios → modelo de amenazas básico → OWASP Top 10 → validación y codificación → secretos → dependencias → logging → revisión de código segura.
- **Autenticación moderna**: contraseñas bien guardadas → sesiones y cookies → MFA → OAuth 2.0 y OIDC → PKCE → tokens (acceso, refresco, rotación) → passkeys → recuperación de cuenta → auditoría.
- **Seguridad web**: modelo de origen → XSS y CSP → CSRF → CORS → cookies → cabeceras → inyección → SSRF → dependencias del front.
- **Seguridad móvil**: modelo de la plataforma → almacenamiento → red → autenticación y biometría → integridad del dispositivo y de la app → ingeniería inversa y hardening → OWASP MASVS y MASTG.
- **Seguridad de APIs**: OWASP API Top 10 → autorización por objeto y por función → exposición de datos → rate limiting → validación de esquemas → tokens → registro y alertas.
- **DevSecOps**: amenazas en CI/CD → SAST y SCA → secretos en pipelines → SBOM y firmas → imágenes de contenedor → políticas.

## Ideas erróneas frecuentes

- «Con HTTPS la app es segura» → protege el transporte, no la lógica ni el control de acceso.
- «Ofuscar protege los secretos» → un secreto dentro del cliente no es secreto; usa el servidor.
- «SHA-256 sirve para contraseñas» → usa Argon2id, scrypt, bcrypt o PBKDF2 con parámetros adecuados.
- «El JWT está cifrado» → normalmente solo está firmado (JWS); cualquiera puede leer su contenido.
- «El flujo implícito es para SPAs y móviles» → usa authorization code con PKCE.
- «Las listas negras bastan para validar» → valida con listas de permitidos y esquemas.
- «El certificate pinning siempre compensa» → puede dejar la app sin conexión si las claves rotan; evalúa el riesgo.
- «Las reglas de complejidad hacen contraseñas fuertes» → NIST prioriza la longitud y las listas de contraseñas comprometidas.
- «CORS es una defensa del servidor» → es una relajación controlada de la política del navegador.

## Decisiones que el estudiante debe saber argumentar

- Sesión con cookie o tokens en el cliente.
- Proveedor de identidad gestionado o propio.
- Pinning, integridad de la app o ninguna de las dos, según el riesgo.
- Qué registrar en logs sin exponer datos personales.
- Nivel de ASVS o MASVS objetivo para el proyecto.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- **OWASP Top 10:2025**: A01 Broken Access Control · A02 Security Misconfiguration · A03 Software Supply Chain Failures · A04 Cryptographic Failures · A05 Injection · A06 Insecure Design · A07 Authentication Failures · A08 Software or Data Integrity Failures · A09 Security Logging and Alerting Failures · A10 Mishandling of Exceptional Conditions.
- **NIST SP 800-63B rev. 4**: contraseñas de al menos 15 caracteres cuando son el único factor (8 como parte de MFA), sin reglas de composición y con listas de bloqueo.
- **RFC 9700** (enero de 2025) recoge las buenas prácticas actuales de seguridad para OAuth 2.0; OAuth 2.1 las consolida (verifica el estado del borrador).
- **Passkeys**: Credential Manager en Android y AuthenticationServices en iOS.
- En Android, `security-crypto` (EncryptedSharedPreferences) está deprecado: usa Keystore.

## Ideas de práctica

- Modelo de amenazas de una funcionalidad real del proyecto, con mitigaciones priorizadas.
- Corregir una vulnerabilidad IDOR en una API propia y añadir el test que la cubre.
- Implementar inicio de sesión con authorization code + PKCE en una app móvil.
- Añadir CSP estricta a una web y resolver lo que rompa.
- Revisar una app con la checklist de OWASP MASVS.
- Pipeline con SCA, SAST y detección de secretos.
