import { ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { HttpExceptionFilter } from './common/http-exception.filter';
import { AppConfigService } from './config/config.service';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  app.useGlobalFilters(new HttpExceptionFilter());
  app.enableCors();

  const config = app.get(AppConfigService);
  await app.listen(config.port);
  console.log(
    `Nest Gateway running on http://localhost:${config.port} -> ${config.aiAgentBaseUrl}`,
  );
}

bootstrap();
