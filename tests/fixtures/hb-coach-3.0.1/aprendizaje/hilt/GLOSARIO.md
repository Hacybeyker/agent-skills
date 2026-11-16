---
tema: "Hilt: inyección de dependencias en Android"
slug: hilt
---

# Glosario · Hilt: inyección de dependencias en Android

| Término | Definición | Lección |
|---|---|---|
| **Binding** | Regla que indica al grafo cómo obtener una instancia de un tipo: un constructor con `@Inject`, un método `@Provides` o un `@Binds`. | [1.3](lecciones/1.3-de-di-manual-a-dagger-grafo-y-codigo-generado.md) |
| **Componente** | Contenedor generado que expone el grafo y fija el tiempo de vida de los objetos con scope. | [1.3](lecciones/1.3-de-di-manual-a-dagger-grafo-y-codigo-generado.md) |
| **Contenedor de dependencias** | Objeto que sabe construir el grafo y decide cuánto vive cada instancia. | [1.2](lecciones/1.2-di-manual-constructor-contenedor-y-fabricas.md) |
| **Dependencia** | Objeto que una clase necesita para cumplir su función. | 1.1 |
| **Fake** | Implementación simple y funcional de una interfaz que se usa en tests en lugar de la real. | [1.2](lecciones/1.2-di-manual-constructor-contenedor-y-fabricas.md) |
| **Grafo de dependencias** | Conjunto de bindings y de las relaciones entre ellos. | [1.3](lecciones/1.3-de-di-manual-a-dagger-grafo-y-codigo-generado.md) |
| **Inversión de control** | Principio por el que un elemento externo, y no la propia clase, decide qué dependencias se usan y cuándo se crean. | 1.1 |
| **Inyección por constructor** | Técnica de DI en la que las dependencias llegan como parámetros del constructor. | [1.2](lecciones/1.2-di-manual-constructor-contenedor-y-fabricas.md) |
| **KSP** | Kotlin Symbol Processing: API para analizar código Kotlin al compilar; Hilt la usa para generar el grafo. | [1.3](lecciones/1.3-de-di-manual-a-dagger-grafo-y-codigo-generado.md) |
| **Service locator** | Patrón en el que la clase pide sus dependencias a un registro global; oculta lo que necesita. | [1.2](lecciones/1.2-di-manual-constructor-contenedor-y-fabricas.md) |
