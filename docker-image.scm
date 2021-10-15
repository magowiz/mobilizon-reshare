(define-module (docker-image)
  #:use-module (gnu)
  #:use-module (gnu packages base)   ;; for coreutils
  #:use-module (gnu packages bash)   ;; for bash
  #:use-module (gnu packages gawk)   ;; for gawk
  #:use-module (gnu packages less)   ;; for less
  #:use-module (guix)
  #:use-module (guix gexp)           ;; for #$ and #~
  #:use-module (mobilizon-reshare)   ;; for mobilizon-reshare.git
  #:use-module (gnu services base)   ;; for special-file-service-type
  #:use-module (gnu services mcron)) ;; for mcron

(define mobilizon-reshare-job
  ;; Run mobilizon-reshare every 15th minute.
  #~(job "*/15 * * * *"
         (string-append #$mobilizon-reshare.git "/bin/mobilizon-reshare start")
         "mobilizon-reshare-start"))

(define mobilizon-reshare-docker-image
  (operating-system
    (locale "it_IT.utf8")
    (timezone "Europe/Rome")
    (keyboard-layout
     (keyboard-layout "it" "nodeadkeys"))

    (bootloader
     (bootloader-configuration
      (bootloader grub-bootloader)))

    (file-systems
     (list
      (file-system
        (mount-point "/")
        (device "/dev/fake")
        (type "ext4"))))

    (host-name "mobilizon-reshare-scheduler")

    (packages
     (list
      mobilizon-reshare.git
      coreutils
      findutils
      less
      grep
      gawk))

    (services
     (list
      (service special-files-service-type
               `(("/bin/sh" ,(file-append bash "/bin/sh"))))
      (service mcron-service-type)
      (simple-service 'mobilizon-reshare-cron-jobs
                      mcron-service-type
                      (list mobilizon-reshare-job))))))

mobilizon-reshare-docker-image