package {{PAQUETE}}

import okhttp3.Request

// "GET /items/{id}": method and path with the segments that look like ids normalized; no query or body.
object HttpSectionName {
    private val ID_SEGMENT = Regex(
        "/(\\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" +
            "|[0-9a-fA-F]{16,})(?=/|$)"
    )

    fun endpoint(request: Request): String = "${request.method} ${sanitize(request.url.encodedPath)}"

    fun sanitize(path: String): String = path.replace(ID_SEGMENT, "/{id}")
}
