import { IsBoolean, IsNotEmpty, IsOptional, IsString } from 'class-validator';

export class GenerateFormDto {
  @IsString()
  @IsNotEmpty()
  requirement: string;

  @IsOptional()
  @IsBoolean()
  need_approval?: boolean;
}
