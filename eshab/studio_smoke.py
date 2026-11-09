"""Exercise the shipped HTML, WebChannel bridge and real exported files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import traceback


def studio_smoke():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu --disable-background-timer-throttling --disable-renderer-backgrounding --disable-features=CalculateNativeWinOcclusion"
    receipt_path = Path(tempfile.gettempdir()) / "Eshab-studio-smoke.json"
    receipt = {"ok": False, "checks": []}
    windows = []
    try:
        from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, Qt
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import QApplication
        from PIL import Image, ImageChops
        import pymupdf as fitz
        from . import paths, settings, theme
        from .studio import StudioWindow

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        for font in ("segoeui.ttf", "segoeuib.ttf", "tahoma.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font))
        with tempfile.TemporaryDirectory(prefix="eshab_studio_") as temp:
            root = Path(temp)
            paths.settings_file = lambda: root / "settings.json"
            settings._cache = None
            settings.set("language", "en")
            theme.apply_app_theme()

            def evaluate(window, expression):
                result = []
                loop = QEventLoop()
                window.page.runJavaScript(expression, lambda value: (result.append(value), loop.quit()))
                QTimer.singleShot(5000, loop.quit)
                loop.exec()
                if not result:
                    raise TimeoutError("The studio renderer did not reply")
                return result[0]

            def wait_for(window, expression, seconds=25):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    value = evaluate(window, expression)
                    if value:
                        return value
                    loop = QEventLoop()
                    QTimer.singleShot(70, loop.quit)
                    loop.exec()
                debug = evaluate(window, "JSON.stringify({stage:globalThis.__studioStage,requests:Array.from(requests.keys()),inline:!!inlineEditor,saving:saving,receipt:globalThis.__studioReceipt})")
                raise TimeoutError(f"Studio condition timed out: {expression}; {debug}")

            pdf_source = root / "letter.pdf"
            doc = fitz.open()
            page = doc.new_page(width=500, height=650)
            page.insert_text((40, 70), "Original title", fontsize=20)
            page.insert_text((40, 120), "Keep this line", fontsize=12)
            doc.save(pdf_source)
            doc.close()
            original = pdf_source.read_bytes()
            pdf_window = StudioWindow("pdf", pdf_source)
            windows.append(pdf_window)
            pdf_window.show()
            wait_for(pdf_window, "typeof pdf !== 'undefined' && !!pdf && !!document.getElementById('stage')")
            evaluate(pdf_window, """
                globalThis.__studioReceipt = null;
                (async () => {
                    globalThis.__studioStage = 'click';
                    const first = pdf.elements.find(e => e.text === 'Original title');
                    const target = document.querySelector('[data-element="' + first.id + '"]');
                    const rect = target.getBoundingClientRect();
                    target.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,cancelable:true,button:0,clientX:rect.left+4,clientY:rect.top+4}));
                    await new Promise(resolve => setTimeout(resolve, 100));
                    globalThis.__studioStage = 'type';
                    if (!inlineEditor || document.activeElement !== inlineEditor.element) throw Error('Click did not focus in-place text');
                    inlineEditor.element.textContent = 'Direct edit works';
                    inlineEditor.element.dispatchEvent(new InputEvent('input', {bubbles:true}));
                    globalThis.__studioStage = 'save';
                    const output = await save();
                    globalThis.__studioReceipt = {ok:true,output,text:pdf.elements.map(e=>e.text).join(' ')};
                })().catch(error => globalThis.__studioReceipt = {ok:false,error:String(error)});
            """)
            pdf_result = json.loads(wait_for(pdf_window, "globalThis.__studioReceipt ? JSON.stringify(globalThis.__studioReceipt) : ''"))
            if not pdf_result.get("ok"):
                raise AssertionError(pdf_result)
            with fitz.open(pdf_result["output"]) as saved:
                text = saved[0].get_text()
                assert "Direct edit works" in text and "Original title" not in text
                assert "Keep this line" in text
            assert pdf_source.read_bytes() == original
            assert "edit 1 - text" in Path(pdf_result["output"]).name
            receipt["checks"].append({"name": "click_type_save_pdf", "ok": True, "output": Path(pdf_result["output"]).name})
            pdf_window.close()

            image_source = root / "photo.png"
            Image.new("RGB", (1200, 800), "white").save(image_source)
            original_image = image_source.read_bytes()
            image_window = StudioWindow("image", image_source)
            windows.append(image_window)
            image_window.show()
            wait_for(image_window, "typeof model !== 'undefined' && !!model?.image && !!document.getElementById('canvas')")
            evaluate(image_window, """
                globalThis.__studioReceipt = null;
                (async () => {
                    await setTool('text');
                    const canvas = document.getElementById('canvas');
                    const rect = canvas.getBoundingClientRect();
                    canvas.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,cancelable:true,button:0,clientX:rect.left+rect.width*.1,clientY:rect.top+rect.height*.2}));
                    await new Promise(resolve => setTimeout(resolve,100));
                    if (!inlineEditor) throw Error('Image text did not open in place');
                    inlineEditor.element.textContent = 'Eshab';
                    inlineEditor.element.dispatchEvent(new InputEvent('input',{bubbles:true}));
                    const output = await save();
                    globalThis.__studioReceipt = {ok:true,output};
                })().catch(error => globalThis.__studioReceipt = {ok:false,error:String(error)});
            """)
            image_result = json.loads(wait_for(image_window, "globalThis.__studioReceipt ? JSON.stringify(globalThis.__studioReceipt) : ''"))
            if not image_result.get("ok"):
                raise AssertionError(image_result)
            with Image.open(image_source) as source, Image.open(image_result["output"]) as saved:
                assert saved.size == (1200, 800)
                assert ImageChops.difference(source.convert("RGB"), saved.convert("RGB")).getbbox()
            assert image_source.read_bytes() == original_image
            receipt["checks"].append({"name": "click_type_save_image", "ok": True, "output": Path(image_result["output"]).name})
            # Check real renderer geometry at the smallest supported window.
            for language in ("en", "ar"):
                evaluate(image_window, f"ar={str(language == 'ar').lower()};document.documentElement.dir=ar?'rtl':'ltr';")
                image_window.resize(880, 620)
                evaluate(image_window, "setTool('draw')")
                wait_for(image_window, "document.getElementById('inspector').offsetWidth > 0")
                layout = json.loads(evaluate(image_window, """
                    JSON.stringify((()=>{
                        const rect=id=>{const r=document.getElementById(id).getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
                        const dock=rect('dock'),stage=rect('stage-scroll'),panel=rect('inspector');
                        const overlap=(a,b)=>Math.min(a.right,b.right)-Math.max(a.x,b.x)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>1;
                        return {overlap:overlap(dock,stage)||overlap(panel,stage),overflow:document.documentElement.scrollWidth>innerWidth,dock,stage,panel};
                    })())
                """))
                assert not layout["overlap"] and not layout["overflow"], layout
                receipt["checks"].append({"name": f"separate_tools_{language}_880px", "ok": True})
            image_window.close()

            import math, struct, wave
            audio_source = root / "صوت.wav"
            with wave.open(str(audio_source), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(b"".join(struct.pack("<h", round(14000*math.sin(i*2*math.pi*440/8000))) for i in range(32000)))
            audio_original = audio_source.read_bytes()
            audio_window = StudioWindow("audio", audio_source)
            windows.append(audio_window)
            audio_window.show()
            wait_for(audio_window, "typeof audioModel !== 'undefined' && !!audioModel?.ready", seconds=30)
            evaluate(audio_window, """
                globalThis.__studioReceipt=null;
                (async()=>{
                    setAudioRange(.6,2.1);
                    const displayed=document.getElementById('audio-selected-duration').textContent;
                    if(displayed!=='00:01.500')throw Error('Incorrect selected duration: '+displayed);
                    await rpc('audioPlay',{start:.6,end:2.1});
                    await rpc('audioStop');
                    const output=await save();
                    globalThis.__studioReceipt={ok:true,output};
                })().catch(error=>globalThis.__studioReceipt={ok:false,error:String(error)});
            """)
            audio_result=json.loads(wait_for(audio_window,"globalThis.__studioReceipt ? JSON.stringify(globalThis.__studioReceipt) : ''",seconds=30))
            assert audio_result.get("ok"),audio_result
            from . import tools
            assert abs(tools.probe_duration_seconds(Path(audio_result["output"]))-1.5)<.03
            assert audio_source.read_bytes()==audio_original
            receipt["checks"].append({"name":"audio_waveform_select_preview_trim_save", "ok":True,"duration":1.5})
            audio_window.close()
            app.processEvents()
            receipt["ok"] = True
    except Exception:
        receipt["traceback"] = traceback.format_exc()
    finally:
        for window in windows:
            try:
                if window.bridge.session:
                    window.bridge.session.dirty = False
                window.close()
            except RuntimeError:
                pass
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True), flush=True)
    return 0 if receipt["ok"] else 1
