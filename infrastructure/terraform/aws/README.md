# Terraform — AWS (scaffold, sin aplicar)

**Este módulo nunca se ha aplicado.** No hay `terraform.tfvars` real, ni credenciales AWS, ni
ejecución de `terraform apply`/`plan` contra ninguna cuenta, en ningún sitio de este repo ni de
CI. Existe únicamente para que el usuario pueda activar un despliegue AWS de verdad más
adelante sin diseñarlo desde cero — ver ADR-6 para el motivo (AWS es un proveedor más
reconocido en un CV/portfolio que Oracle Cloud, pero su free tier de 12 meses con
`t2.micro`/`t3.micro` de 1GB de RAM no cubre este stack sin coste).

## Qué declara (equivalente a `oracle/`, mismo nivel de abstracción)

- VPC + subnet pública + internet gateway + tabla de rutas.
- Security Group abierto solo a 22 (SSH, restringido a `ssh_allowed_cidr`), 80 y 443 — mismo
  criterio que `oracle/`.
- Una única instancia EC2 (no ECS, no RDS gestionado, no ALB) corriendo el mismo
  `docker-compose.yml` del repo vía su propio `cloud-init.tftpl` — deliberadamente sin
  automatismos ARM-específicos de Oracle (esta AMI es amd64, no hace falta esperar/montar un
  volumen de bloque dedicado como en Oracle, el volumen raíz ya está dimensionado vía
  `root_volume_size_gb`).

No reutiliza ningún recurso de `infrastructure/terraform/oracle/` — son providers Terraform
distintos (`aws` vs `oci`) sin solapamiento real de esquema, ver ADR-6 para el razonamiento
completo de por qué no se fuerza una abstracción compartida.

## Qué falta rellenar antes de poder aplicar de verdad

Ninguno de estos valores vive en el repo — el usuario los aporta en su propio
`terraform.tfvars` (nunca versionado) el día que decida activarlo:

1. **Cuenta AWS** con facturación activa — a diferencia de Oracle Always Free, **esto ya no es
   gratis de forma indefinida**. `t2.micro`/`t3.micro` (free tier de 12 meses) no tienen RAM
   suficiente para este stack (ver ADR-6); un tamaño realista (p. ej. `t3.medium`, 4GB) tiene
   coste desde el primer minuto.
2. **Región AWS real** a usar (`aws_region`, `availability_zone`) — el valor por defecto en
   `variables.tf` (`eu-west-1`) es un placeholder, no una recomendación.
3. **Tipo de instancia real**, dimensionado contra el consumo de memoria real del stack antes
   de comprometerse a un tamaño y su coste mensual.
4. **Par de credenciales AWS** (access key + secret key de un usuario/rol IAM con permisos para
   crear VPC/EC2/Security Groups) configuradas donde el provider `aws` las espera (variables de
   entorno `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, perfil de `~/.aws/credentials`, o SSO) —
   **no se declaran como variable de Terraform**, es la forma estándar/recomendada de
   autenticar el provider `aws` sin que la credencial pase por ningún `.tf`/`.tfvars`.
5. **Clave SSH pública propia** y **tu IP pública** en CIDR, igual que en `oracle/`.
6. **URL del repo** y los mismos secretos de aplicación que en `oracle/terraform.tfvars.example`
   (`postgres_password`, `minio_secret_key`, `jwt_secret_key`, `grafana_admin_password`, etc.).

## Comandos

```bash
cd infrastructure/terraform/aws
terraform init
terraform validate   # esto es lo único que se ejecuta de forma rutinaria/en CI sobre este módulo
```

`terraform plan`/`terraform apply` se dejan **deliberadamente fuera** de cualquier automatismo
— solo el usuario, con sus propias credenciales AWS y tras copiar `terraform.tfvars.example` a
un `terraform.tfvars` real, debe ejecutarlos cuando decida activar este scaffold.

## Lo que no se pudo verificar en este entorno

Igual que en `oracle/README.md`: sin binario `terraform` disponible en este sandbox, no se pudo
ejecutar `terraform init`/`validate` contra el registro real del provider `aws`. La sintaxis se
escribió con la mayor confianza posible (es el provider de Terraform más documentado y estable
que existe), pero queda pendiente de una verificación real por parte del usuario antes de
confiar en que compila sin ajustes.
