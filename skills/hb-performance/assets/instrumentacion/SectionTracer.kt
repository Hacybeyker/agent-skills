package {{PAQUETE}}

import android.os.Build
import android.os.Trace

/**
 * Secciones de traza para hb-performance. Vive solo en debug y profiling: release no la compila.
 * La interfaz permite testear sin Android con un tracer falso.
 */
interface SectionTracer {
    fun beginSection(name: String)

    fun endSection()

    fun beginAsyncSection(name: String, cookie: Int)

    fun endAsyncSection(name: String, cookie: Int)
}

/** `android.os.Trace` acepta nombres de hasta 127 caracteres. */
const val MAX_SECTION_NAME = 127

fun sectionName(name: String): String = name.take(MAX_SECTION_NAME)

/** Las secciones asíncronas existen desde Android 10 (API 29), lo mismo que `profileable`. */
object PlatformSectionTracer : SectionTracer {
    override fun beginSection(name: String) = Trace.beginSection(sectionName(name))

    override fun endSection() = Trace.endSection()

    override fun beginAsyncSection(name: String, cookie: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) Trace.beginAsyncSection(sectionName(name), cookie)
    }

    override fun endAsyncSection(name: String, cookie: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) Trace.endAsyncSection(sectionName(name), cookie)
    }
}
