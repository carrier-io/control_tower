node {
  properties([pipelineTriggers([pollSCM('* * * * *')])])
  try {
    stage('Checkout') {
      git credentialsId: 'control_tower',
        url: 'git@github.com:carrier-io/control_tower.git'
      message = sh(returnStdout: true, script: "git log -1 HEAD --pretty=format:'%s'").trim()
    }
    stage('Zip') {
      docker.image("greene1337/zipthis").inside {
          sh "cp package/requirements.txt . && cp package/lambda.py . && pip3 install -r requirements.txt -t . && zip -r control-tower.zip . -x Jenkinsfile -x package/* -x *.git* && mv control-tower.zip package/control-tower.zip"
      }
    }
    stage('Push') {
      if (message == "Auto Commit") {
        print "[Debug] Skipping stage"
      }
      else {
        sshagent(['control_tower']) {
          sh 'git add package/control-tower.zip && git commit -m "Auto Commit" && git push origin master'
        }
      }
    }
  }
  catch (ex) {
    throw ex
  }
  finally {
    cleanWs()
    sh 'docker rmi greene1337/zipthis --force'
  }
}
