"""Local interface-language policy tests; no cloud or model calls."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ui_locale import resolve_locale,error_message,gpu_info


class LocaleTests(unittest.TestCase):
    def test_manual_cookie_then_weighted_browser_preference_then_english_fallback(self):
        self.assertEqual(resolve_locale('lighttry_lang=zh','en-US,en;q=0.8'),'zh')
        self.assertEqual(resolve_locale('lighttry_lang=en','zh-CN'),'en')
        self.assertEqual(resolve_locale('', 'fr-FR, zh-TW;q=0.9, en-US;q=0.8'),'zh')
        self.assertEqual(resolve_locale('', 'en-US;q=0.5, zh-CN;q=1'),'zh')
        self.assertEqual(resolve_locale('', 'fr-FR'),'en')
        self.assertEqual(resolve_locale('', ''),'en')
        self.assertEqual(resolve_locale('lighttry_lang=other','zh-CN'),'zh')

    def test_errors_keep_codes_but_translate_display_message(self):
        self.assertIn('JPG',error_message('en','INVALID_IMAGE','只接受 JPG。'))
        self.assertEqual(error_message('zh','INVALID_IMAGE','只接受 JPG。'),'只接受 JPG。')
        self.assertNotIn('中文',error_message('en','UNKNOWN_CODE','中文'))

    def test_gpu_display_translation_preserves_state_and_stop_proof(self):
        source={'state':'STOPPING','monitor':{'verifiedStopped':False,'instancesEmpty':False},
                'diagnostic':{'code':'OPERATOR_STOP','active':True,'severity':'warning',
                              'title':'GPU正在停止','detail':'停机原因：操作者请求停机。'},
                'message':'停机请求已提交。'}
        translated=gpu_info('en',source)
        self.assertEqual(translated['state'],'STOPPING')
        self.assertEqual(translated['diagnostic']['code'],'OPERATOR_STOP')
        self.assertIn('GPU stopping',translated['message'])
        self.assertIn('charges may continue',translated['message'])
        self.assertEqual(source['diagnostic']['title'],'GPU正在停止')
        self.assertIs(gpu_info('zh',source),source)


if __name__=='__main__':unittest.main()
