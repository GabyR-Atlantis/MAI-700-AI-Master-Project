# MAI-700-AI-Master-Project

# App de generación de comentarios y documentación de código de lenguaje de programación

## **Plan de entrega por semana**

| Módulo | Actividad principal | Entregable | Dependencia |
| ----- | ----- | ----- | ----- |
| **Módulo 2** | Investigar antecedentes, seleccionar fuentes y preparar los datos. Definir la línea base ética, incluyendo licencias MIT, Apache 2.0 y BSD. | **E1. Dataset documentado \+ antecedentes \+ criterios éticos** | **Inicio del proyecto. No depende de otro entregable.** |
| **Módulo 3** | Analizar los datos, establecer una línea base y seleccionar el método de IA más apropiado. | **E2. Línea base \+ método seleccionado** | **Depende de E1.** Los datos preparados en M2 son necesarios para comparar métodos. **Bloquea E3.** |
| **Módulo 4** | Implementar el núcleo de la aplicación y conectar la entrada de código con la generación de documentación. | **E3. Prototipo funcional de generación** | **Depende de E2.** El método seleccionado debe estar definido antes de implementar. **Bloquea E4.** |
| **Módulo 5** | Evaluar el prototipo, aplicar los criterios de éxito y analizar errores y casos fallidos. | **E4. Evaluación \+ análisis de fallos** | **Depende de E3.** Se necesita un prototipo funcional para evaluarlo. **Bloquea E5.** |
| **Módulo 6** | Revisar riesgos de IA responsable, sesgos, privacidad, licencias, errores y necesidad de revisión humana. | **E5. Revisión de IA responsable \+ plan de mitigación** | **Depende de E4.** Los resultados y fallos identificados orientan la revisión responsable. **Bloquea E6.** |
| **Módulo 7** | Empaquetar la aplicación, preparar documentación de uso y realizar pruebas finales de funcionamiento. | **E6. Aplicación empaquetada \+ documentación técnica y de usuario** | **Depende de E5.** Los riesgos y controles deben estar definidos antes del empaquetado final. **Bloquea E7.** |
| **Semana 7 – Módulo 8** | Preparar la defensa, presentación, demostración y entrega final del proyecto. | **E7. Presentación \+ demostración \+ proyecto final** | **Depende de E6.** La aplicación y documentación deben estar terminadas antes de la defensa. |

### **Dependencias críticas**

La cadena principal de dependencias será:

**E1 → E2 → E3 → E4 → E5 → E6 → E7**

Los entregables **E1, E2, E3, E4, E5 y E6 bloquean directamente el siguiente paso**. Esto significa que un retraso importante en cualquiera de ellos puede afectar las semanas posteriores.

Para reducir este riesgo, las tareas de documentación, limpieza de datos y preparación de la presentación podrán realizarse parcialmente en paralelo cuando no dependan del entregable anterior.

# **Registro de riesgos**

| Riesgo | Probabilidad | Impacto | Mitigación concreta |
| ----- | ----- | ----- | ----- |
| **1\. No conseguir suficientes datos de código y documentación con las licencias permitidas** | Media | **Alto** | Comenzar la búsqueda en M2 y mantener varias fuentes alternativas con MIT, Apache 2.0 y BSD. |
| **2\. El modelo no alcanza el 80 % de corrección establecido** | Media | **Alto** | Evaluar una línea base desde M3 y probar métodos alternativos antes de llegar a la implementación final. |
| **3\. Los datos contienen duplicados o ejemplos de baja calidad** | Alta | Medio | Realizar limpieza, eliminación de duplicados y revisión de muestras antes de dividir entrenamiento y prueba. |
| **4\. El prototipo requiere más tiempo del previsto** | Media | **Alto** | Mantener un alcance mínimo: generación de documentación para funciones o fragmentos de código, sin agregar funcionalidades secundarias. |
| **5\. La documentación generada contiene errores que no son detectados automáticamente** | Media | Alto | Incorporar evaluación humana y establecer un límite máximo de 10 % de errores graves. |
| **6\. Problemas de licencia o procedencia de los datos** | Baja | **Alto** | Registrar la fuente y licencia de cada conjunto utilizado y excluir cualquier material cuya licencia no pueda verificarse. |
| **7\. El despliegue o empaquetado presenta problemas técnicos** | Media | Medio | Preparar una versión local ejecutable como alternativa al despliegue completo y probarla antes de M7. |

## **Plan alternativo para el riesgo de mayor impacto**

El riesgo de mayor impacto considerado es que **el modelo no alcance los criterios de éxito**, especialmente el mínimo de 80 % de corrección. Este riesgo podría impedir que la aplicación principal cumpla el objetivo planteado.

Si se materializa, en lugar de intentar construir una aplicación generativa más compleja, se reducirá el alcance y se construirá un **prototipo asistido de documentación de código basado en un enfoque híbrido**.

Este prototipo utilizará análisis estructurado del código para identificar elementos como funciones, parámetros, valores de retorno y nombres de variables, y combinará esta información con plantillas o generación de texto controlada. El sistema seguirá produciendo comentarios y documentación, pero limitará la generación libre cuando exista mayor riesgo de introducir información incorrecta.

La ventaja de este plan es que conserva el **objetivo principal del proyecto —ayudar a documentar código—** aunque el modelo generativo no alcance el rendimiento esperado. También permitiría demostrar una solución funcional, medible y con revisión humana, en lugar de presentar un modelo que no cumple los criterios establecidos.

### **Hito final**

Al terminar el Módulo 8, el proyecto deberá contar con:

* Datos documentados y con licencias verificadas.  
* Método de IA seleccionado y justificado.  
* Prototipo funcional.  
* Evaluación contra los umbrales establecidos.  
* Análisis de errores.  
* Revisión de IA responsable.  
* Aplicación y documentación empaquetadas.  
* Presentación y demostración final.  
* **Plan alternativo ejecutable si el modelo principal no cumple los criterios de éxito.**

*Todavía no estoy seguro de esta idea así que lo que está en este documento es temporario y pudiera cambiar.*
