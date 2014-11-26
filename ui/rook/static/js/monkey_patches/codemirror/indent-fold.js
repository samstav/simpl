CodeMirror.registerHelper("fold", "indent", function(cm, start) {
  var foldEnded = function(myIndent, currColumn, prevColumn, lastLineNumber) {
    return ( (currColumn < myIndent) ||
             (currColumn == myIndent && prevColumn >= myIndent) ||
             (currColumn > myIndent && i == lastLineNumber) );
  }

  var lastLineNumber = cm.lineCount() - 1,
      tabSize = cm.getOption("tabSize"),
      firstLine = cm.getLine(start.line),
      myIndent = CodeMirror.countColumn(firstLine, null, tabSize),
      maxColumn = myIndent;

  if (firstLine.trim() == "") return;

  for (var i = start.line + 1 ; i <= lastLineNumber ; i++) {
    var prevLine = cm.getLine(i-1);
    var currLine = cm.getLine(i);
    if (currLine.trim() == "" && i < lastLineNumber) continue;

    var prevColumn = CodeMirror.countColumn(prevLine, null, tabSize);
    var currColumn = CodeMirror.countColumn(currLine, null, tabSize);
    maxColumn = Math.max(currColumn, maxColumn);

    if (foldEnded(myIndent, currColumn, prevColumn, lastLineNumber)) {
      if (maxColumn <= myIndent) return;

      var lastFoldLineNumber = (currColumn > myIndent && i == lastLineNumber) ? i : i-1;
      var lastFoldLine = cm.getLine(lastFoldLineNumber);

      return {from: CodeMirror.Pos(start.line, firstLine.length),
              to: CodeMirror.Pos(lastFoldLineNumber, lastFoldLine.length)};
    }
  }
});
CodeMirror.indentRangeFinder = CodeMirror.fold.indent; // deprecated

