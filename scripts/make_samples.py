from pathlib import Path
import io
import pymupdf as f
from PIL import Image,ImageDraw
root=Path('test-output');root.mkdir(exist_ok=True)
im=Image.new('RGB',(900,600),'#171d35');p=ImageDraw.Draw(im);p.rounded_rectangle((100,100,800,500),45,fill='#aea1ff');p.text((300,270),'ESHAB',fill='#171d35',font_size=65);im.save(root/'Orbit sample.png')
doc=f.open();page=doc.new_page(width=595,height=842)
page.insert_text((48,65),'A little room for your ideas.',fontname='helv',fontsize=25,color=(.17,.15,.33))
page.insert_text((48,103),'Click this text to replace it. The image below is editable too.',fontsize=11,color=(.4,.43,.55))
page.insert_image((48,145,547,478),filename=str(root/'Orbit sample.png'))
fonts=Path('C:/Windows/Fonts');css="@font-face{font-family:Arabic;src:url(tahoma.ttf)}body{font-family:Arabic;font-size:20pt;color:#41396a}"
page.insert_htmlbox(f.Rect(48,535,547,620),'<p dir="rtl">ملفاتك، على طريقتك. جرّب تعديل النص والصورة.</p>',css=css,archive=f.Archive(str(fonts)))
page.insert_text((48,770),'ESHAB / PDF STUDIO',fontsize=9,color=(.6,.6,.7))
doc.new_page(width=595,height=842).insert_text((48,65),'Your second page.',fontsize=25)
doc.save(root/'Edit me.pdf');doc.close()
print(root.resolve())
