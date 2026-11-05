package {{PAQUETE}}

import okhttp3.Request
import retrofit2.Invocation
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HEAD
import retrofit2.http.HTTP
import retrofit2.http.OPTIONS
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT

/**
 * "GET items/{id}": método y ruta como plantilla, sin IDs, query ni body. La plantilla sale de la anotación
 * de Retrofit; sin Retrofit (o con @Url), se normalizan los segmentos que parecen IDs.
 */
object HttpSectionName {
    private val ID_SEGMENT = Regex(
        "/(\\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" +
            "|[0-9a-fA-F]{16,})(?=/|$)"
    )

    fun endpoint(request: Request): String = "${request.method} ${template(request)}"

    fun sanitize(path: String): String = path.replace(ID_SEGMENT, "/{id}")

    private fun template(request: Request): String {
        val method = request.tag(Invocation::class.java)?.method()
        val fromRetrofit = method?.annotations?.firstNotNullOfOrNull { annotation ->
            when (annotation) {
                is GET -> annotation.value
                is POST -> annotation.value
                is PUT -> annotation.value
                is PATCH -> annotation.value
                is DELETE -> annotation.value
                is HEAD -> annotation.value
                is OPTIONS -> annotation.value
                is HTTP -> annotation.path
                else -> null
            }
        }
        return fromRetrofit?.takeIf { it.isNotEmpty() } ?: sanitize(request.url.encodedPath)
    }
}
