"""Small orthographic textured skin renderer; Qt raster only, no WebEngine."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPainter,QImage,QTransform,QColor,QPen,QFont
from PySide6.QtWidgets import QWidget
from .theme import paint_color


class SkinPreview(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.image=QImage();self.yaw=-.38;self.pitch=.16;self.drag=None;self.slim=False;self._textures={}
        self.setMinimumSize(220,320);self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAccessibleName('皮肤三维预览，左右旋转、上下俯仰，双击复位');self.setToolTip('拖动旋转 / 上下俯仰 · 双击复位')

    def load(self,path,slim=False):
        from ..skins import skin_bytes
        image=QImage.fromData(skin_bytes(path))
        if image.isNull() or image.width()!=64 or image.height() not in (32,64):raise ValueError('皮肤 PNG 无法解码')
        self.image=image;self.slim=slim;self._textures.clear();self.update()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag=QPointF(event.position());self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept()
    def mouseMoveEvent(self,event):
        if self.drag is not None:
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self.drag=None;self.setCursor(Qt.CursorShape.OpenHandCursor);return
            delta=event.position()-self.drag;self.drag=QPointF(event.position())
            self.yaw=math.remainder(self.yaw+delta.x()*.012,math.tau)
            self.pitch=max(-math.pi/2+.02,min(math.pi/2-.02,self.pitch-delta.y()*.009))
            self.update();event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.drag=None;self.setCursor(Qt.CursorShape.OpenHandCursor);event.accept()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag=None;self.yaw=-.38;self.pitch=.16;self.setCursor(Qt.CursorShape.OpenHandCursor);self.update();event.accept()
    def hideEvent(self,event):
        self.drag=None;self.setCursor(Qt.CursorShape.OpenHandCursor);super().hideEvent(event)

    def texture(self,rect,shade):
        key=(self.image.cacheKey(),tuple(rect),shade)
        if key not in self._textures:
            texture=self.image.copy(*rect)
            if shade!=1:
                for yy in range(texture.height()):
                    for xx in range(texture.width()):
                        color=texture.pixelColor(xx,yy)
                        texture.setPixelColor(xx,yy,QColor(round(color.red()*shade),round(color.green()*shade),round(color.blue()*shade),color.alpha()))
            self._textures[key]=texture
        return self._textures[key]

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.image.isNull():
            painter.setPen(paint_color(self,'muted',text=True));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'导入皮肤后预览');return
        unit=min(self.width()/24,self.height()/38);cx=self.width()/2;cy=self.height()/2-16*unit
        yaw=self.yaw;pitch=self.pitch
        def project(point):
            x,y,z=point;xx=x*math.cos(yaw)+z*math.sin(yaw);zz=-x*math.sin(yaw)+z*math.cos(yaw)
            yy=(y-16)*math.cos(pitch)-zz*math.sin(pitch);depth=(y-16)*math.sin(pitch)+zz*math.cos(pitch)
            return QPointF(cx+xx*unit,cy+(yy+16)*unit),depth
        faces=[]
        def cube(x,y,z,w,h,d,uv,inflate=0,rotate_bottom=False):
            x-=inflate;y-=inflate;z-=inflate;w+=2*inflate;h+=2*inflate;d+=2*inflate
            points=[(x,y,z+d),(x+w,y,z+d),(x+w,y+h,z+d),(x,y+h,z+d),
                    (x,y,z),(x+w,y,z),(x+w,y+h,z),(x,y+h,z)]
            indices=[(0,1,2,3),(5,4,7,6),(4,0,3,7),(1,5,6,2),(4,5,1,0),(3,2,6,7)]
            if rotate_bottom:
                # Rotate the head underside UVs 180 degrees, including its overlay.
                indices[5]=(6,7,3,2)
            for corners,rect,shade in zip(indices,uv,(1.0,.80,.72,.86,1.0,.60)):
                projected=[project(points[i]) for i in corners];poly=[item[0] for item in projected]
                # All faces sorted by camera depth; rear surfaces paint first.
                texture=self.texture(rect,shade)
                faces.append((sum(p[1] for p in projected)/4,poly,texture))
        def uv(u,v,w,h,d):
            return [(u+d,v+d,w,h),(u+2*d+w,v+d,w,h),(u,v+d,d,h),(u+d+w,v+d,d,h),(u+d,v,w,d),(u+d+w,v,w,d)]
        arm=3 if self.slim else 4;modern=self.image.height()==64
        cube(-4,0,-4,8,8,8,uv(0,0,8,8,8),rotate_bottom=True)
        cube(-4,8,-2,8,12,4,uv(16,16,8,12,4))
        cube(-4-arm,8,-2,arm,12,4,uv(40,16,arm,12,4))
        cube(4,8,-2,arm,12,4,uv(32,48,arm,12,4) if modern else uv(40,16,arm,12,4))
        cube(-4,20,-2,4,12,4,uv(0,16,4,12,4))
        cube(0,20,-2,4,12,4,uv(16,48,4,12,4) if modern else uv(0,16,4,12,4))
        cube(-4,0,-4,8,8,8,uv(32,0,8,8,8),.35,rotate_bottom=True)
        if modern:
            cube(-4,8,-2,8,12,4,uv(16,32,8,12,4),.18)
            cube(-4-arm,8,-2,arm,12,4,uv(40,32,arm,12,4),.18)
            cube(4,8,-2,arm,12,4,uv(48,48,arm,12,4),.18)
            cube(-4,20,-2,4,12,4,uv(0,32,4,12,4),.18)
            cube(0,20,-2,4,12,4,uv(0,48,4,12,4),.18)
        for depth,p,texture in sorted(faces,key=lambda face:face[0]):
            if texture.isNull():continue
            tw,th=texture.width(),texture.height();a,b,c=p[0],p[1],p[3]
            if abs((b.x()-a.x())*(c.y()-a.y())-(b.y()-a.y())*(c.x()-a.x()))<.001:continue
            painter.save();painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
            painter.setTransform(QTransform((b.x()-a.x())/tw,(b.y()-a.y())/tw,
                (c.x()-a.x())/th,(c.y()-a.y())/th,a.x(),a.y()))
            painter.drawImage(QPointF(0,0),texture);painter.restore()
        painter.setPen(paint_color(self,'muted',text=True));font=QFont(self.font());font.setPixelSize(11);painter.setFont(font)
        painter.drawText(QRectF(0,self.height()-23,self.width(),20),Qt.AlignmentFlag.AlignCenter,'拖动旋转 · 双击复位')
