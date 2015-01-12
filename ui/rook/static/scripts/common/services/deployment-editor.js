angular.module('checkmate.DeploymentData')
  .directive('deploymentEditor', function(DeploymentData, $timeout, Blueprint) {
    return {
      restrict: 'E',
      replace: true,
      scope: {},
      template: '<checkmate-codemirror checkmate-codemirror-opts="codemirror.options" ng-model="deployment"></checkmate-codemirror>',
      controller: function($scope) {
        $scope.deployment = '';
        $scope.valid = true; // Is the YAML valid?
        $scope.dirty = false; // Out of sync with topology
        $scope.submitting = false; // Waiting on response?

        $scope.codemirror = {
          editor: null,
          editorAltered: false,
          isFocused: false,
          markAltered: function() {
            $scope.codemirror.editorAltered = true;
          },
          foldFunction: CodeMirror.newFoldFunction(CodeMirror.fold.indent),
          foldDefault: function(editor) {
            var inBlueprint = false;
            editor.eachLine(function(line) {
              if (line.text.substring(0, 1) !== ' ') {
                if (line.text.substring(0, 10) == 'blueprint:') {
                  inBlueprint = true;
               } else {
                  inBlueprint = false;
                  $scope.codemirror.foldFunction(editor, editor.getLineNumber(line));
                }
              } else if (inBlueprint && line.text.substring(0, 10) === '  options:') {
                $scope.codemirror.foldFunction(editor, editor.getLineNumber(line));
              } else if (inBlueprint && line.text.substring(0, 12) === '  meta-data:') {
                $scope.codemirror.foldFunction(editor, editor.getLineNumber(line));
              }
            });
          },
          setEditorDefaultState: function(editor) {
            $scope.codemirror.foldDefault(editor);
          }
        };

        $scope.codemirror.options = {
          lint: typeof CodeMirror.lint.yaml !== 'undefined',
          mode: 'yaml',
          theme: 'lesser-dark',
          lineNumbers: true,
          autoFocus: true,
          lineWrapping: true,
          dragDrop: false,
          matchBrackets: true,
          foldGutter: true,
          extraKeys: {"Ctrl-Q": function(cm){ cm.foldCode(cm.getCursor()); }},
          gutters: ['CodeMirror-lint-markers','CodeMirror-linenumbers', 'CodeMirror-foldgutter'],
          onGutterClick: function(editor, start) {
            $scope.codemirror.markAltered();
            return $scope.codemirror.foldFunction(editor, start);
          },
          onLoad: function(_editor) {
            _editor.on("change", function(d) {
              try {
                var deployment = jsyaml.load($scope.deployment);
                $scope.$emit('editor:nsync');
                DeploymentData.set(deployment);
              } catch(e) {
                $scope.$emit('editor:out_of_sync');
                $scope.$apply();
              }
            });
          },
          onFocus: function() {
            $scope.codemirror.markAltered();
            $scope.codemirror.isFocused = true;
            $scope.$emit('editor:focus');
          },
          onBlur: function() {
            $scope.codemirror.isFocused = false;
            $scope.$emit('editor:blur');
          }
        };

        $scope.$on('editor:refreshed', function(event, editor, viewData) {
          $scope.codemirror.setEditorDefaultState(editor);
        });

        $scope.$on('deployment:update', function(event, data) {
          if(!$scope.codemirror.isFocused) {
            var yamlData = jsyaml.safeDump(data);

            if ($scope.deployment != yamlData) {
              $timeout(function() {
                $scope.deployment = yamlData;
              });
            }
          }
        });

      }
    };
  });
