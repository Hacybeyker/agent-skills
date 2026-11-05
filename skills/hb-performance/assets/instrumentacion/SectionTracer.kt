package {{PAQUETE}}

import android.annotation.SuppressLint
// hb-perf:red>
import android.os.Build
// <hb-perf:red
import android.os.Trace

// Trace sections for hb-performance. Lives only in debug and profiling: release never compiles it.
interface SectionTracer {
    fun beginSection(name: String)

    fun endSection()
    // hb-perf:red>

    fun beginAsyncSection(name: String, cookie: Int)

    fun endAsyncSection(name: String, cookie: Int)
    // <hb-perf:red
}

// android.os.Trace takes names up to 127 characters.
const val MAX_SECTION_NAME = 127

fun sectionName(name: String): String = name.take(MAX_SECTION_NAME)

object PlatformSectionTracer : SectionTracer {
    // The matching endSection runs in another callback (lifecycle pre/post), which Lint cannot follow.
    @SuppressLint("UnclosedTrace")
    override fun beginSection(name: String) = Trace.beginSection(sectionName(name))

    override fun endSection() = Trace.endSection()
    // hb-perf:red>

    override fun beginAsyncSection(name: String, cookie: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) Trace.beginAsyncSection(sectionName(name), cookie)
    }

    override fun endAsyncSection(name: String, cookie: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) Trace.endAsyncSection(sectionName(name), cookie)
    }
    // <hb-perf:red
}
