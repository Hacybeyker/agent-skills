# Dominio: criptografía aplicada

Mapa para enseñar a usar criptografía correctamente en aplicaciones. El objetivo es que el estudiante elija primitivas y librerías adecuadas, las use sin errores y entienda los ataques a nivel conceptual. No se diseñan algoritmos propios.

## Límites de la enseñanza

Enseña a proteger sistemas propios. Explica los ataques clásicos (reutilización de nonce, padding oracle, timing) para entender por qué existen las defensas, sin preparar herramientas para romper sistemas de terceros.

## Mapa de competencias

### 🟢 Básico
- Objetivos: confidencialidad, integridad, autenticidad y no repudio.
- Cifrado simétrico frente a asimétrico; hash frente a MAC frente a firma.
- Codificar no es cifrar (Base64, hex).
- Aleatoriedad criptográfica (CSPRNG) frente a generadores comunes.
- Regla de oro: usar librerías de alto nivel y bien auditadas.

### 🟡 Intermedio
- **Cifrado autenticado (AEAD)**: AES-GCM y ChaCha20-Poly1305; nonces únicos por clave; por qué ECB y CBC sin MAC son peligrosos.
- **Integridad**: SHA-2 y SHA-3, HMAC, comparación en tiempo constante.
- **Derivación de claves**: HKDF para claves; Argon2id, scrypt, bcrypt o PBKDF2 para contraseñas, con sal y parámetros de coste.
- **Asimétrica**: RSA frente a curvas elípticas (P-256, X25519, Ed25519); intercambio de claves (ECDH); firmas (ECDSA, Ed25519).
- **TLS y PKI**: handshake de TLS 1.3 a alto nivel, certificados, cadenas de confianza, revocación.
- **APIs de plataforma**: Web Crypto, CryptoKit, Android Keystore, Tink, libsodium.

### 🟠 Avanzado
- **Gestión de claves**: generación, almacenamiento en hardware (TEE, StrongBox, Secure Enclave), rotación, cifrado por sobres (envelope encryption) con KMS.
- **Protocolos**: HPKE, JOSE (JWS y JWE) y sus trampas, cifrado de extremo a extremo a nivel conceptual.
- **Ataques y defensas**: reutilización de nonce, padding oracle, canales laterales de tiempo, ataques de degradación.
- **Certificados**: pinning, Certificate Transparency.
- **Criptoagilidad**: diseñar para poder cambiar de algoritmo.

### 🔴 Experto
- Criptografía poscuántica: ML-KEM (FIPS 203), ML-DSA (FIPS 204), SLH-DSA (FIPS 205).
- Esquemas híbridos (por ejemplo, X25519 + ML-KEM en TLS) y planes de transición.
- Cumplimiento (FIPS 140-3) y auditorías.
- Diseño de protocolos siempre con revisión experta.

## Rutas típicas

- **Criptografía aplicada para desarrolladores**: conceptos → aleatoriedad → hashes → HMAC → AEAD → derivación de claves → asimétrica → firmas → TLS → gestión de claves → errores comunes → proyecto.
- **Almacenamiento seguro en móvil**: amenazas en el dispositivo → Keychain y Keystore → claves respaldadas por hardware → biometría ligada a claves → cifrar datos locales → rotación y migración (por ejemplo, salir de EncryptedSharedPreferences).
- **Contraseñas y autenticación**: hash lento y sal → parámetros de coste → pepper → migración de hashes antiguos → passkeys.
- **TLS y PKI**: por qué TLS → handshake → certificados → validación → configuración de servidor → pinning → Certificate Transparency.
- **Preparación poscuántica**: amenaza «recolectar ahora, descifrar después» → qué algoritmos se ven afectados → estándares de NIST → híbridos → inventario y criptoagilidad.

## Ideas erróneas frecuentes

- «Base64 es cifrado» → es una codificación reversible sin clave.
- «MD5 o SHA-1 sirven para seguridad» → tienen colisiones prácticas; usa SHA-256 o superior.
- «AES-CBC es suficiente» → sin MAC no hay integridad; usa AEAD.
- «El IV o nonce debe ser secreto» → no, pero en GCM debe ser único por clave y en CBC impredecible.
- «Cifro las contraseñas» → se guardan con una función de hash lenta y sal.
- «`Random` sirve para generar claves» → usa `SecureRandom`, `SecRandomCopyBytes` o `crypto.getRandomValues`.
- «Guardo la clave junto a los datos cifrados» → usa Keystore, Keychain o un KMS.
- «Los ordenadores cuánticos rompen AES» → afectan sobre todo a RSA y curvas elípticas; AES-256 sigue siendo adecuado.
- «Más bits siempre es mejor» → AES-128 es seguro; cada tamaño tiene costes.

## Decisiones que el estudiante debe saber argumentar

- AES-GCM o ChaCha20-Poly1305 según plataforma y hardware.
- Argon2id, scrypt, bcrypt o PBKDF2 según entorno y requisitos.
- RSA o curvas elípticas; Ed25519 o ECDSA P-256 según interoperabilidad.
- Librería de alto nivel (Tink, libsodium, CryptoKit) o primitivas de bajo nivel.
- Claves en hardware del dispositivo o en un KMS del servidor.

## Panorama actual (verificado en septiembre de 2026; revisar antes de enseñar)

- NIST publicó FIPS 203, 204 y 205 (agosto de 2024) y seleccionó HQC como mecanismo de encapsulación adicional (marzo de 2025).
- NIST propone un calendario de transición que depreca los algoritmos vulnerables a computación cuántica hacia 2030 y los retira hacia 2035 (verifica el estado del documento NIST IR 8547).
- El intercambio de claves híbrido X25519 + ML-KEM ya se usa ampliamente en TLS.
- CryptoKit incluye ML-KEM y ML-DSA desde iOS 26.
- En Android, `security-crypto` está deprecado: usa Android Keystore directamente o Tink.
- NIST SP 800-63B rev. 4 marca los requisitos actuales para contraseñas.

## Ideas de práctica

- Cifrar y descifrar un archivo con AEAD usando la librería de la plataforma, con pruebas de manipulación.
- Migrar hashes de contraseñas antiguos a Argon2id al iniciar sesión.
- Guardar un token con una clave de hardware protegida por biometría.
- Configurar TLS en un servidor y validarlo con herramientas públicas.
- Inventario criptográfico de un proyecto con propuesta de migración poscuántica.
