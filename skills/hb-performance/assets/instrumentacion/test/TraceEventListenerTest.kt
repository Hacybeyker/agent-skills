package {{PAQUETE}}

import java.io.IOException
import okhttp3.OkHttpClient
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Test

class TraceEventListenerTest {
    private val call = OkHttpClient().newCall(Request.Builder().url("https://api.test/items/42?token=x").build())

    @Test
    fun completedCallOpensAndClosesHttpAndTtfbWithoutIdsOrQuery() {
        val tracer = RecordingTracer()
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
    fun failedCallClosesTheOpenSections() {
        val tracer = RecordingTracer()
        val listener = TraceEventListener(call, tracer)
        listener.callStart(call)
        listener.requestHeadersEnd(call, call.request())
        listener.callFailed(call, IOException("offline"))
        val opened = tracer.events.count { it.startsWith("beginAsync") }
        val closed = tracer.events.count { it.startsWith("endAsync") }
        assertEquals(opened, closed)
    }

    @Test
    fun sanitizeReplacesNumericIdsAndUuids() {
        assertEquals("/a/{id}/b/{id}", HttpSectionName.sanitize("/a/123/b/123e4567-e89b-12d3-a456-426614174000"))
    }

    private class RecordingTracer : SectionTracer {
        val events = mutableListOf<String>()

        override fun beginSection(name: String) {
            events += "begin $name"
        }

        override fun endSection() {
            events += "end"
        }

        override fun beginAsyncSection(name: String, cookie: Int) {
            events += "beginAsync $name"
        }

        override fun endAsyncSection(name: String, cookie: Int) {
            events += "endAsync $name"
        }
    }
}
