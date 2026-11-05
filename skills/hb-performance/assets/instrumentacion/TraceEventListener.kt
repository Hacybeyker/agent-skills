package {{PAQUETE}}

import java.io.IOException
import java.util.concurrent.atomic.AtomicInteger
import okhttp3.Call
import okhttp3.EventListener
import okhttp3.Request

/**
 * HTTP <endpoint>: la llamada completa, incluida la lectura del body (de callStart a callEnd o callFailed).
 * TTFB <endpoint>: del fin de los headers del request al primer byte de la respuesta (≈ servidor + red).
 * Secciones asíncronas: las llamadas concurrentes se ven solapadas. Requiere OkHttp 4 o superior.
 * Se registra con builder.eventListenerFactory(TraceEventListener.FACTORY); OkHttp admite un solo factory.
 */
class TraceEventListener(call: Call, private val tracer: SectionTracer = PlatformSectionTracer) : EventListener() {
    private val endpoint = HttpSectionName.endpoint(call.request())
    private val callName = "HTTP $endpoint"
    private val ttfbName = "TTFB $endpoint"
    private val callCookie = COOKIES.incrementAndGet()
    private var ttfbCookie = 0
    private var open = false

    override fun callStart(call: Call) {
        open = true
        tracer.beginAsyncSection(callName, callCookie)
    }

    override fun requestHeadersEnd(call: Call, request: Request) {
        endTtfb() // una redirección o un reintento cierra el TTFB anterior
        ttfbCookie = COOKIES.incrementAndGet()
        tracer.beginAsyncSection(ttfbName, ttfbCookie)
    }

    override fun responseHeadersStart(call: Call) = endTtfb()

    override fun callEnd(call: Call) = finish()

    override fun callFailed(call: Call, ioe: IOException) = finish()

    private fun finish() {
        endTtfb()
        if (open) tracer.endAsyncSection(callName, callCookie)
        open = false
    }

    private fun endTtfb() {
        if (ttfbCookie != 0) tracer.endAsyncSection(ttfbName, ttfbCookie)
        ttfbCookie = 0
    }

    companion object {
        private val COOKIES = AtomicInteger()

        val FACTORY: EventListener.Factory = object : EventListener.Factory {
            override fun create(call: Call): EventListener = TraceEventListener(call)
        }
    }
}
