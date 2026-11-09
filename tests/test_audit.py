import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from image_resizing_claim_audit import phrases as p
from image_resizing_claim_audit.audit import evidence, match_phrases, claims, scan, main

class AuditTests(unittest.TestCase):
    def test_phrase_oracle(self):
        self.assertEqual(p.IMAGERESIZING, ['image resizing', 'image-resizing', 'imageresizing', 'image rescaling', 'image-rescaling', 'image scaling', 'image-scaling', 'photo resizing', 'photo-resizing', 'picture resizing', 'resize images', 'resizes images', 'resizing images', 'resize photos', 'resizes photos', 'resizing photos', 'resize pictures', 'resizes pictures', 'resizing pictures', 'scale images', 'scales images', 'scaling images', 'scale photos', 'scales photos', 'resize an image', 'resizes an image', 'resizing an image', 'resize the image', 'resizes the image', 'resizing the image', 'resize images to', 'resize image to', 'resize images to any size', 'resize images to a specific size', 'image resize tool', 'image resize library', 'image resize feature', 'image resize support', 'supports image resizing', 'image resizing capability', 'image resizing pipeline', 'image resizing algorithm', 'image resizing software', 'image resizing app', 'image resizing model', 'automatic image resizing', 'automated image resizing', 'image resizer', 'image resizers', 'resize image dimensions'])

    def test_denial_oracle(self):
        self.assertEqual(p.NOIMAGERESIZING, ['does not support image resizing', 'do not support image resizing', "doesn't support image resizing", "don't support image resizing", 'no image resizing', 'without image resizing', 'never performs image resizing', 'does not perform image resizing', 'image resizing not supported', 'image resizing unsupported', 'no image resizing support', 'lacks image resizing', 'missing image resizing', 'image resizing disabled', 'no image resizing capability', 'without image resizing support', 'does not provide image resizing', 'no image resizing model', 'image resizing not available', 'does not use image resizing', 'no image rescaling', 'without image rescaling', 'does not support image rescaling', 'no image resizing feature'])

    def test_generic_oracle(self):
        self.assertEqual(p.GENERIC_NAMES, ['resize_image', 'resize_images', 'resize_photo', 'resize_photos', 'resize_picture', 'resize_pictures', 'scale_image', 'scale_images', 'rescale_image', 'rescale_images', 'resize_to', 'resize_image_to', 'resize_to_size', 'scale_image_to', 'rescale_image_to', 'resize_and_save', 'resize_image_file', 'resize_image_dimensions', 'resize_image_width', 'resize_image_height', 'resize_for_thumbnail', 'create_thumbnail', 'make_thumbnail', 'generate_thumbnail'])

    def test_route_oracles(self):
        self.assertEqual(p.PIL_METHODS, ['resize', 'thumbnail'])
        self.assertEqual(p.PIL_FIT, 'PIL.ImageOps.fit')
        self.assertEqual(p.CV_FUNCTION, 'cv2.resize')
        self.assertEqual(p.SKIMAGE_FUNCTION, 'skimage.transform.resize')
        self.assertEqual(p.RESIZE_CLASSES, ['Resize'])
        self.assertEqual(p.RESIZE_SOURCES, ['torchvision.transforms', 'torchvision.transforms.v2'])
        self.assertEqual(p.RESIZE_REQUIRES_CALL, True)

    def test_pillow_routes(self):
        for imp, image, ops in [('from PIL import Image, ImageOps','Image','ImageOps'), ('from PIL import Image as I, ImageOps as O','I','O'), ('import PIL','PIL.Image','PIL.ImageOps'), ('import PIL as P','P.Image','P.ImageOps')]:
            for method in ['resize','thumbnail']:
                for code in ['im = '+image+'.open(path)\nim.'+method+'(size)', image+'.open(path).'+method+'(size)']:
                    with self.subTest(code=code): self.assertTrue(evidence(imp+'\n'+code))
            self.assertTrue(evidence(imp+'\n'+ops+'.fit(im, size)'))

    def test_function_routes(self):
        for imp, call in [('import cv2','cv2.resize'), ('import cv2 as c','c.resize'), ('from cv2 import resize','resize'), ('from cv2 import resize as r','r'), ('import skimage.transform','skimage.transform.resize'), ('import skimage.transform as t','t.resize'), ('from skimage import transform','transform.resize'), ('from skimage import transform as t','t.resize'), ('from skimage.transform import resize','resize'), ('from skimage.transform import resize as r','r')]:
            self.assertTrue(evidence(imp+'\n'+call+'(im, size)'), imp)

    def test_transform_routes(self):
        for imp, ctor in [('from torchvision.transforms import Resize','Resize'), ('from torchvision.transforms.v2 import Resize','Resize'), ('from torchvision.transforms.v2 import Resize as R','R'), ('import torchvision.transforms','torchvision.transforms.Resize'), ('import torchvision.transforms as t','t.Resize'), ('from torchvision import transforms','transforms.Resize'), ('import torchvision.transforms.v2','torchvision.transforms.v2.Resize'), ('from torchvision.transforms import v2','v2.Resize')]:
            for code in ['r='+ctor+'(size)\nr(im)',ctor+'(size)(im)']:
                self.assertTrue(evidence(imp+'\n'+code), code)
            self.assertFalse(evidence(imp+'\nr='+ctor+'(size)'))

    def test_generic_routes(self):
        for name in p.GENERIC_NAMES:
            for code in ['x.'+name+'(im)', 'from other import '+name+'\n'+name+'(im)', 'from other import '+name+' as f\nf(im)']:
                self.assertTrue(evidence(code),code)
            self.assertFalse(evidence(name+'(im)'))

    def test_rejections(self):
        cases=['import PIL, cv2, skimage, torchvision', 'from PIL import Image\nImage.open(path)', 'im.resize(size)', 'im.thumbnail(size)', 'ndarray.resize(size)', 'import numpy as np\nnp.resize(a,size)', 'Tensor.resize_(size)', 'other.resize(im,size)', 'resize(im,size)', 'Resize(size)(im)', 'other.Resize(size)(im)', 'PIL.Image.open(path).resize(size)', 'PIL.ImageOps.fit(im,size)', 'cv2.resize(im,size)', 'skimage.transform.resize(im,size)', 'torchvision.transforms.Resize(size)(im)', 'from PIL import Image\nImage.open(path).crop(box)', 'from PIL import Image\nImage.open(path).rotate(90)', 'from PIL import Image\nImage.open(path).transpose(mode)', 'import cv2\ncv2.flip(im,0)\ncv2.rotate(im,0)', 'a[:, :5]', '"x.resize_image(im)" # cv2.resize(im,size)', 'def f():\n    """resize images"""', 'x.resize_image', 'from cv2 import resize\nresize', 'import subprocess\nsubprocess.run(["resize", "a.jpg"])', 'invalid syntax !']
        cases += ['x.'+name+'(im)' for name in ['upscale','classify','caption','generate','inpaint','colorize','remove_background','detect_objects','stitch']]
        for code in cases:
            with self.subTest(code=code): self.assertFalse(evidence(code))

    def test_shadowing(self):
        routes=[('from PIL import Image','resize','Image.open(path).resize(size)'), ('from PIL import Image','thumbnail','Image.open(path).thumbnail(size)'), ('from PIL import Image','Image','Image.open(path).resize(size)'), ('from PIL import ImageOps','ImageOps','ImageOps.fit(im,size)'), ('from cv2 import resize','resize','resize(im,size)'), ('from skimage.transform import resize','resize','resize(im,size)'), ('from torchvision.transforms import Resize','Resize','Resize(size)(im)'), ('from x import resize_image','resize_image','resize_image(im)'), ('from cv2 import resize as r','r','r(im,size)'), ('from PIL import Image as I','I','I.open(path).resize(size)')]
        for imp,name,call in routes:
            for definition in ['def '+name+'(*args): pass', 'class '+name+': pass']:
                self.assertFalse(evidence(imp+'\n'+definition+'\n'+call),call)
        for name in p.GENERIC_NAMES:
            self.assertFalse(evidence('def '+name+'(): pass\nx.'+name+'(im)'))

    def test_matching(self):
        self.assertEqual(claims('does not support image resizing'), ([], ['does not support image resizing']))
        for phrase in ['image resizing model','resize images to any size']:
            self.assertEqual(claims(phrase)[0],[phrase])
        self.assertEqual(claims('IMAGE RESIZING')[0],['image resizing'])
        self.assertEqual(claims('we scale images to the range 0 to 1')[0],['scale images'])
        self.assertEqual(claims('image scaling for the model input pipeline')[0],['image scaling'])
        self.assertEqual(claims('```py\nimage resizing\n```')[0],[])
        self.assertEqual(claims('`image resizing`')[0],['image resizing'])
        self.assertEqual(claims('image--resizing')[0],[])

    def fixture(self, files, args=()):
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in files.items():
                path=Path(tmp)/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
            out=io.StringIO(); err=io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code=main(['audit', tmp]+list(args))
            return code, out.getvalue(), err.getvalue()

    def test_cli(self):
        rule='documented-image-resizing-claim-false'
        denial='documented-no-image-resizing-claim-false'
        self.assertEqual(self.fixture({'README.md':'image resizing', 'app.py':'x.resize_image()'})[0],0)
        code,out,_=self.fixture({'README.md':'IMAGE RESIZING'}, ['--json']); self.assertEqual(code,2)
        finding=json.loads(out)['findings'][0]
        self.assertEqual(finding['rule'],rule); self.assertEqual(finding['severity'],'high')
        self.assertIn('verdict',finding); self.assertIn('message',finding)
        for args, expected in [([],0), (['--fail-on','medium'],2)]:
            self.assertEqual(self.fixture({'tests/test_fixture.py':'"image resizing"'},args)[0],expected)
        code,out,_=self.fixture({'README.md':'no image resizing','app.py':'x.resize_image()'}); self.assertEqual(code,2); self.assertIn(denial,out)
        self.assertEqual(self.fixture({'README.md':'hello'})[0],0)
        self.assertEqual(self.fixture({'README.md':'no image resizing'})[0],0)
        self.assertEqual(self.fixture({'docs/guide.md':'image resizing'},['--ignore','docs/'])[0],0)
        self.assertEqual(self.fixture({'README.md':'image resizing','a.py':'from PIL import Image\nm=Image.open(path)', 'b.py':'m.resize(size)'})[0],2)
        self.assertEqual(self.fixture({'README.md':'image resizing','venv/a.py':'x.resize_image()'})[0],2)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'README.md').write_text('hello')
            self.assertEqual(main(['audit','--ignore','docs/',tmp]),0)
        out=io.StringIO()
        with contextlib.redirect_stdout(out): self.assertEqual(main(['--version']),0)
        self.assertEqual(out.getvalue().strip(),'0.1.0')
        self.assertEqual(main(['audit','/nonexistent-claim-audit-path']),1)
        self.assertEqual(main(['--unknown']),1)

    def test_readme_self_audit(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(claims((root/'README.md').read_text()), ([],[]))
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'README.md').write_text((root/'README.md').read_text())
            self.assertEqual(scan(Path(tmp))[0],[])

    def test_scope_and_collapse(self):
        code,out,_=self.fixture({'README.md':'image resizing image resizer', 'docs/a.md':'resizes images'})
        self.assertEqual(code,2)
        self.assertEqual(out.count('documented-image-resizing-claim-false'),1)
        self.assertEqual(self.fixture({'other.md':'image resizing'})[0],0)
        self.assertEqual(self.fixture({'docs/deep/guide.md':'image resizing'})[0],2)
        self.assertEqual(self.fixture({'README.md':'image resizing', 'pkg/model.py':'x.resize_image()'})[0],0)
        self.assertEqual(self.fixture({'README.md':'image resizing', '.git/model.py':'x.resize_image()'})[0],2)
        self.assertEqual(self.fixture({'README.md':'image resizing', 'custom/pyvenv.cfg':'', 'custom/model.py':'x.resize_image()'})[0],2)
        self.assertEqual(self.fixture({'README.md':'image resizing', 'ignored/model.py':'x.resize_image()'}, ['--ignore','ignored/'])[0],2)
        self.assertEqual(self.fixture({'README.md':'image resizing','docs/a.md':'image resizing'}, ['--ignore','README','--ignore','docs/'])[0],0)
        code,out,err=self.fixture({'README.md':'hello'}, ['--verbose','--json'])
        self.assertEqual(code,0); self.assertEqual(json.loads(out)['verdict'],'PASS')
        self.assertIn('Scope:',err); self.assertIn('README.md:',err)

    def test_full_checkout_medium(self):
        root=Path(__file__).resolve().parents[1]
        findings,_=scan(root)
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0]['severity'],'medium')

if __name__ == '__main__': unittest.main()
