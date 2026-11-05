package {{PAQUETE}}

import android.app.Application
import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.net.Uri

/**
 * Registra ScreenTraceCallbacks al arrancar la app, sin tocar la Application: Android crea los content
 * providers antes de Application.onCreate. Se declara solo en los manifests de debug y profiling.
 */
class PerfInstaller : ContentProvider() {
    override fun onCreate(): Boolean {
        (context?.applicationContext as? Application)?.registerActivityLifecycleCallbacks(ScreenTraceCallbacks())
        return true
    }

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?
    ): Cursor? = null

    override fun getType(uri: Uri): String? = null

    override fun insert(uri: Uri, values: ContentValues?): Uri? = null

    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0

    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        selectionArgs: Array<out String>?
    ): Int = 0
}
