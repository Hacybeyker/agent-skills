package {{PAQUETE}}

import org.junit.Assert.assertEquals
import org.junit.Test

class SectionTracerTest {
    @Test
    fun sectionNameRecortaA127Caracteres() {
        assertEquals(MAX_SECTION_NAME, sectionName("x".repeat(300)).length)
        assertEquals("HTTP GET items", sectionName("HTTP GET items"))
    }

    @Test
    fun navigationTraceAbreYCierraUnaMarca() {
        val tracer = FakeTracer()
        NavigationTrace.tracer = tracer
        NavigationTrace.mark("Detail")
        assertEquals(listOf("begin NAV Detail", "end"), tracer.events)
    }
}

class FakeTracer : SectionTracer {
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
