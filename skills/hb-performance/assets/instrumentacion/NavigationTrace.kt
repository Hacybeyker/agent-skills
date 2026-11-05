package {{PAQUETE}}

// NAV <destination>: one instant mark per destination change, fed by a hook in the main code that does nothing in
// release (see references/setup.md of hb-performance).
object NavigationTrace {
    var tracer: SectionTracer = PlatformSectionTracer

    fun mark(destination: Any) {
        tracer.beginSection("NAV ${destinationName(destination)}")
        tracer.endSection()
    }

    // Route templates ("movie/{id}") and data class or data object names ("Detail(id=1)" -> "Detail") survive R8
    // and carry no ids.
    fun destinationName(destination: Any): String = when (destination) {
        is String -> destination.substringBefore('?')
        else -> destination.toString().substringBefore('(').substringBefore('@')
    }
}
