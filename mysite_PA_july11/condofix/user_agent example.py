from user_agents import parse
from flask import request
def code_exemple():

    ua_string = request.form['specs']
    user_agent = parse(ua_string)
    #print('agent:', request.form['specs'])#.get('specs'))
    # print(user_agent.browser)
    # print(user_agent.device)  # returns Device(family=u'iPhone', brand=u'Apple', model=u'iPhone')
    # print('mobile:',user_agent.is_mobile)  # returns True
    # print('tablet:',user_agent.is_tablet)  # returns False
    # print('pc:',user_agent.is_pc)  # returns False
    cell=0
    #vérifier si l'usager utilise un téléphone cellulaire
    if user_agent.is_mobile==True and user_agent.is_tablet==False:
      cell=1


    if cell==1:
        return 'specific web page'

# html code
# <input type="hidden" id="demo" name="specs">
# <script>
# let agent = navigator.userAgent;
# document.getElementById("demo").value = "User-agent:<br>" + agent;
# document.getElementById("curso").defaultValue = window.location.href.substring(91);
# </script>