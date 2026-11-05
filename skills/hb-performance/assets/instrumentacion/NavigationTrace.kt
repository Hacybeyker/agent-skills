package {{PAQUETE}}

/**
 * NAV <destino>: una marca por cambio de destino. Se llama desde el punto único donde el proyecto navega,
 * a través de un gancho que en release no hace nada (ver references/setup.md de hb-performance).
 */
object NavigationTrace {
    var tracer: SectionTracer = PlatformSectionTracer

    fun mark(destination: String) {
        tracer.beginSection("NAV $destination")
        tracer.endSection()
    }
}
