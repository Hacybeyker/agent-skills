package {{PAQUETE}}

import java.io.IOException
import java.net.InetSocketAddress
import java.net.Proxy
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TraceEventListenerTest {
    private val call = OkHttpClient().newCall(Request.Builder().url("https://api.test/items/42").build())

    @Test
    fun completedCallTracesQueueConnectionAndTtfbInsideHttp() {
        val tracer = RecordingTracer()
        val listener = TraceEventListener(call, tracer)
        val address = InetSocketAddress.createUnresolved("api.test", 443)
        listener.callStart(call)
        listener.dnsStart(call, "api.test")
        listener.connectStart(call, address, Proxy.NO_PROXY)
        listener.connectEnd(call, address, Proxy.NO_PROXY, Protocol.HTTP_2)
        listener.requestHeadersEnd(call, call.request())
        listener.responseHeadersStart(call)
        listener.callEnd(call)
        assertEquals(
            listOf(
                "beginAsync HTTP GET /items/{id}",
                "beginAsync QUEUE GET /items/{id}",
                "endAsync QUEUE GET /items/{id}",
                "beginAsync CONN GET /items/{id}",
                "endAsync CONN GET /items/{id}",
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
    fun queryBecomesAShortTagSoOtherParametersAreNotDuplicates() {
        fun name(url: String) = HttpSectionName.endpoint(Request.Builder().url(url).build())
        val page1 = name("https://api.test/items?page=1")
        assertTrue(page1, page1.matches(Regex("GET /items #[0-9a-f]{4}")))
        assertNotEquals(page1, name("https://api.test/items?page=2"))
        assertEquals(page1, name("https://api.test/items?page=1"))
        assertEquals("GET /items", name("https://api.test/items"))
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
