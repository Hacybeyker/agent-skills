package {{PAQUETE}}

import android.app.Activity
import android.app.Application
import android.os.Bundle

/**
 * SCREEN <Clase> <evento>: cuánto duran onCreate, onStart y onResume de cada actividad (callbacks pre y post,
 * Android 10+). Para apps sin fragments; las pantallas de Compose se marcan con NavigationTrace.
 * No toca el código de las pantallas: lo registra PerfInstaller.
 */
class ScreenTraceCallbacks(private val tracer: SectionTracer = PlatformSectionTracer) :
    Application.ActivityLifecycleCallbacks {

    override fun onActivityPreCreated(activity: Activity, savedInstanceState: Bundle?) =
        tracer.beginSection(screen(activity, "onCreate"))

    override fun onActivityPostCreated(activity: Activity, savedInstanceState: Bundle?) = tracer.endSection()

    override fun onActivityPreStarted(activity: Activity) = tracer.beginSection(screen(activity, "onStart"))

    override fun onActivityPostStarted(activity: Activity) = tracer.endSection()

    override fun onActivityPreResumed(activity: Activity) = tracer.beginSection(screen(activity, "onResume"))

    override fun onActivityPostResumed(activity: Activity) = tracer.endSection()

    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit

    override fun onActivityStarted(activity: Activity) = Unit

    override fun onActivityResumed(activity: Activity) = Unit

    override fun onActivityPaused(activity: Activity) = Unit

    override fun onActivityStopped(activity: Activity) = Unit

    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit

    override fun onActivityDestroyed(activity: Activity) = Unit

    private fun screen(owner: Any, event: String) = "SCREEN ${owner.javaClass.simpleName} $event"
}
