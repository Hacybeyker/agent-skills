package {{PAQUETE}}

import java.io.IOException
import okhttp3.OkHttpClient
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Test

class TraceEventListenerTest {
    private val call = OkHttpClient().newCall(Request.Builder().url("https://api.test/items/42?token=x").build())

    @Test
    fun llamadaCompletaAbreYCierraHttpYTtfbSinIdsNiQuery() {
        val tracer = FakeTracer()
        val listener = TraceEventListener(call, tracer)
        listener.callStart(call)
        listener.requestHeadersEnd(call, call.request())
        listener.responseHeadersStart(call)
        listener.callEnd(call)
        assertEquals(
            listOf(
                "beginAsync HTTP GET /items/{id}",
                "beginAsync TTFB GET /items/{id}",
                "endAsync TTFB GET /items/{id}",
                "endAsync HTTP GET /items/{id}"
            ),
            tracer.events
        )
    }

    @Test
    fun unaLlamadaFallidaCierraLasSeccionesAbiertas() {
        val tracer = FakeTracer()
        val listener = TraceEventListener(call, tracer)
        listener.callStart(call)
        listener.requestHeadersEnd(call, call.request())
        listener.callFailed(call, IOException("sin red"))
        val opened = tracer.events.count { it.startsWith("beginAsync") }
        val closed = tracer.events.count { it.startsWith("endAsync") }
        assertEquals(opened, closed)
    }

    @Test
    fun sanitizeNormalizaIdsNumericosYUuids() {
        assertEquals("/a/{id}/b/{id}", HttpSectionName.sanitize("/a/123/b/123e4567-e89b-12d3-a456-426614174000"))
    }
}
