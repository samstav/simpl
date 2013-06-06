giant = function(){
  var w = 960,
  h = 500;

  d3.select(".entries").select("svg").remove();
  var vis = d3.select(".entries").append("svg:svg")
      .attr("width", w)
      .attr("height", h);
  var tasks = [

    {
        "startDate": new Date("Sun Dec 09 01:36:45 EST 2012"),
            "endDate": new Date("Sun Dec 09 02:36:45 EST 2012"),
                "taskName": "E Job",
                    "status": "FAILED"
  },

  {
        "startDate": new Date("Sun Dec 09 04:56:32 EST 2012"),
            "endDate": new Date("Sun Dec 09 06:35:47 EST 2012"),
                "taskName": "A Job",
                    "status": "RUNNING"
  }];
  var taskStatus = {
    "SUCCEEDED" : "bar",
    "FAILED" : "bar-failed",
    "RUNNING" : "bar-running",
    "KILLED" : "bar-killed"
  };
  var taskNames = [ "D Job", "P Job", "E Job", "A Job", "N Job" ];
  var gantt = d3.gantt().taskTypes(taskNames).taskStatus(taskStatus);
  gantt(tasks);
}

batman = function(){
  var w = 960,
  h = 500;

  d3.select(".entries").select("svg").remove();
  var vis = d3.select(".entries").append("svg:svg")
      .attr("width", w)
      .attr("height", h);
  var nodes = _.map(data, function(t, k) {return t;});
  var circle = vis.selectAll("circle").data(nodes);;

  var nter = circle.enter().append("circle");
  enter.attr("cy", function(d) {
    console.log(d)
    try {
      var resource_number = parseInt(d.properties.resource);
    } catch(err) {
      var resource_number = 0;
    }
    return 100 + 45* resource_number;
  });

  enter.attr("cx", 160);

  enter.attr("r", function(d) {
    try {
      var resource_number = parseInt(d.properties.resource);
    } catch(err) {
      var resource_number = 0;
    }
    return Math.sqrt(100 + 15*resource_number);
  });
}
