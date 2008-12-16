/*
  A simple class for displaying file information and progress
  Note: This is a demonstration only and not part of SWFUpload.
  Note: Some have had problems adapting this class in IE7. It may not be suitable for your application.
*/

// Constructor
// file is a SWFUpload file object
// targetID is the HTML element id attribute that the FileProgress HTML structure will be added to.
// Instantiating a new FileProgress object with an existing file will reuse/update the existing DOM elements
function FileProgress(file, targetID) {
  this.fileProgressID = file.id;

  this.opacity = 100;
  this.height = 0;

  this.fileProgressWrapper = document.getElementById(this.fileProgressID);
  if (!this.fileProgressWrapper) {
    this.fileProgressWrapper = document.createElement("tr");
    this.fileProgressWrapper.className = "progressWrapper";
    this.fileProgressWrapper.id = this.fileProgressID;

    this.fileProgressElement = document.createElement("td");
    this.fileProgressElement.className = "progressContainer";
    //this.fileProgressElement.setAttribute('colspan', '6');
    //this.fileProgressElement.setAttribute('style', 'text-align:center;');


    var progressCancel = document.createElement("a");
    progressCancel.className = "progressCancel";
    progressCancel.href = "#";
    progressCancel.style.visibility = "hidden";
    progressCancel.appendChild(document.createTextNode("Cancel"));

    var progressText = document.createElement("span");
    progressText.className = "progressName";
    progressText.appendChild(document.createTextNode(file.name));

    var progressBar = document.createElement("span");
    progressBar.className = "progressBarInProgress";

    var progressStatus = document.createElement("span");
    progressStatus.className = "progressBarStatus";
    progressStatus.innerHTML = "&nbsp;";

    this.fileProgressElement.appendChild(progressCancel);
    this.fileProgressElement.appendChild(progressText);
    this.fileProgressElement.appendChild(progressStatus);
    this.fileProgressElement.appendChild(progressBar);

    this.fileProgressWrapper.appendChild(document.createElement('td'));
    this.fileProgressWrapper.appendChild(document.createElement('td'));
    this.fileProgressWrapper.appendChild(this.fileProgressElement);
    this.fileProgressWrapper.appendChild(document.createElement('td'));
    this.fileProgressWrapper.appendChild(document.createElement('td'));
    this.fileProgressWrapper.appendChild(document.createElement('td'));
    this.fileProgressWrapper.appendChild(document.createElement('td'));
    this.fileProgressWrapper.appendChild(document.createElement('td'));

    var tbody = jQuery('#songlist tbody').get(0);
    tbody.appendChild(this.fileProgressWrapper);

    //tbody.down('tr').insert({after: tr});
    //tbody.insert({after: this.fileProgressWrapper});
    //tbody.appendChild(this.fileProgressWrapper);
    //document.getElementById(targetID).appendChild(this.fileProgressWrapper);
  } else {
    //this.fileProgressElement = this.fileProgressWrapper.firstChild;
    this.fileProgressElement = this.fileProgressWrapper.childNodes[2];
  }

  this.height = this.fileProgressWrapper.offsetHeight;

}

FileProgress.prototype.setProgress = function (percentage) {
  this.fileProgressElement.className = "progressContainer green";
  this.fileProgressElement.childNodes[2].className = "progressBarInProgress";
  this.fileProgressElement.childNodes[2].style.width = percentage + "%";
};

FileProgress.prototype.setComplete = function () {
  this.fileProgressElement.className = "progressContainer blue";
  this.fileProgressElement.childNodes[2].className = "progressBarComplete";
  this.fileProgressElement.childNodes[2].style.width = "";

  var oSelf = this;
  oSelf.disappear();

  //setTimeout(function () {
  //
  //}, 1000);
};

FileProgress.prototype.setError = function () {
  this.fileProgressElement.className = "progressContainer red";
  this.fileProgressElement.childNodes[2].className = "progressBarError";
  this.fileProgressElement.childNodes[2].style.width = "";

  var oSelf = this;
  setTimeout(function () {
    oSelf.disappear();
  }, 5000);
};

FileProgress.prototype.setCancelled = function () {
  this.fileProgressElement.className = "progressContainer";
  this.fileProgressElement.childNodes[2].className = "progressBarError";
  this.fileProgressElement.childNodes[2].style.width = "";

  var oSelf = this;
  setTimeout(function () {
    oSelf.disappear();
  }, 2000);
};

FileProgress.prototype.setStatus = function (status) {
  this.fileProgressElement.childNodes[2].innerHTML = status;
};

// Show/Hide the cancel button
FileProgress.prototype.toggleCancel = function (show, swfUploadInstance) {
  this.fileProgressElement.childNodes[0].style.visibility = show ? "visible" : "hidden";
  if (swfUploadInstance) {
    var fileID = this.fileProgressID;
    this.fileProgressElement.childNodes[0].onclick = function () {
      swfUploadInstance.cancelUpload(fileID);
      return false;
    };
  }
};

// Fades out and clips away the FileProgress box.
FileProgress.prototype.disappear = function () {

  var reduceOpacityBy = 15;
  var reduceHeightBy = 4;
  var rate = 30;    // 15 fps

  if (this.opacity > 0) {
    this.opacity -= reduceOpacityBy;
    if (this.opacity < 0) {
      this.opacity = 0;
    }

    if (this.fileProgressWrapper.filters) {
      try {
        this.fileProgressWrapper.filters.item("DXImageTransform.Microsoft.Alpha").opacity = this.opacity;
      } catch (e) {
        // If it is not set initially, the browser will throw an error.  This
        // will set it if it is not set yet.
        this.fileProgressWrapper.style.filter = "progid:DXImageTransform.Microsoft.Alpha(opacity=" + this.opacity + ")";
      }
    } else {
      this.fileProgressWrapper.style.opacity = this.opacity / 100;
    }
  }

  if (this.height > 0) {
    this.height -= reduceHeightBy;
    if (this.height < 0) {
      this.height = 0;
    }

    this.fileProgressWrapper.style.height = this.height + "px";
  }

  if (this.height > 0 || this.opacity > 0) {
    var oSelf = this;
    setTimeout(function () {
      oSelf.disappear();
    }, rate);
  } else {
    this.fileProgressWrapper.style.display = "none";
  }
};
