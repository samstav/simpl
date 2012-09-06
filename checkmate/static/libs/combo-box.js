function activate(field) {
  field.disabled=false;
  if(document.styleSheets)field.style.visibility  = 'visible';
  field.focus(); }
function last_choice(selection) {
  return selection.selectedIndex==selection.length - 1; }
function process_choice(selection,textfield) {
  if(last_choice(selection)) {
    activate(textfield); }
  else {
    textfield.disabled = true;    
    if(document.styleSheets)textfield.style.visibility  = 'hidden';
    textfield.value = ''; }}
function valid(menu,txt) {
  if(menu.selectedIndex == 0) {
    alert('You must make a selection from the menu');
    return false;} 
  if(txt.value == '') {
    if(last_choice(menu)) {
      alert('You need to type your choice into the text box');
      return false; }
    else {
      return true; }}
  else {
    if(!last_choice(menu)) {
      alert('Incompatible selection');
      return false; }
    else {
      return true; }}}
function check_choice() {
  if(!last_choice(document.demoform.menu)) {
    document.demoform.choicetext.blur();
    alert('Please check your menu selection first');
    document.demoform.menu.focus(); }}

