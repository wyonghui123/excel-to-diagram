"""Find where status field is rendered"""
import sys
import json as json_mod
sys.path.insert(0, 'd:/filework/excel-to-diagram')
sys.path.insert(0, 'd:/filework/excel-to-diagram/test_helpers')

from browser_auth_cli import PlaywrightCLI


def test():
    cli = PlaywrightCLI()
    try:
        cli.new_context()
        cli.wait_for_timeout(500)
        cli.authenticated_navigate('/detail/user/1')
        cli.wait_for_timeout(5000)
        cli.screenshot('find_status.png')

        r = cli.evaluate(
            'JSON.stringify((function(){'
            'var el=document.querySelector(".object-page__content");'
            'return el?el.innerText.substring(0,2000):"NO CONTENT";'
            '})())'
        )
        print('[1] 表单内容:')
        print(r)
        print('')

        script = (
            'var results=[];'
            'var keys=["active","inactive","locked","pending"];'
            'var els=document.querySelectorAll("span,div,td,a,p,b,strong");'
            'for(var i=0;i<els.length;i++){'
            '  var el=els[i];'
            '  var text=el.innerText.trim();'
            '  if(text.length>1&&text.length<30){'
            '    for(var j=0;j<keys.length;j++){'
            '      if(text.toLowerCase().indexOf(keys[j].toLowerCase())>=0){'
            '        results.push({text:text,tag:el.tagName,cls:el.className.substring(0,40)});'
            '        break;'
            '      }'
            '    }'
            '  }'
            '}'
            'return JSON.stringify(results.slice(0,50));'
        )
        r2 = cli.evaluate(script)
        if r2:
            try:
                vals = json_mod.loads(r2)
                print('[2] 含状态元素:')
                for v in vals:
                    print('  ' + str(v))
            except Exception as ex:
                print('[2] parse error: ' + str(ex) + ' raw: ' + r2)

        return True

    except Exception as e:
        print('[ERROR] ' + str(e))
        import traceback
        traceback.print_exc()
        return False
    finally:
        cli.close()


if __name__ == '__main__':
    test()
